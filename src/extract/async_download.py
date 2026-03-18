import asyncio
import aiohttp
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional
from src.utils.env_loader import config
from src.utils.log_handler import logger
from src.monitoring.prometheus_stats import metrics

class AsyncDownloader:
    def __init__(self, base_url: Optional[str] = None, save_path: Optional[str] = None, **kwargs):
        self.share_token = "YggdBLfdninEJX9"
        self.webdav_base = "https://arquivos.receitafederal.gov.br/public.php/webdav"
        self.save_path = Path(save_path) if save_path else config.RAW_DIR
        self.semaphore = asyncio.Semaphore(config.MAX_DOWNLOADS)
        self.timeout_seconds = 3600
        # Permite configurar via .env ou usa o mais recente
        self.target_dir = os.getenv("RECEITA_TARGET_DIR", "2026-03")

    async def _discover_latest_folder(self, session: aiohttp.ClientSession) -> str:
        """Descobre automaticamente a pasta mais recente (YYYY-MM)"""
        url = f"{self.webdav_base}/"
        auth = aiohttp.BasicAuth(self.share_token, "")
        headers = {"Depth": "1"}

        logger.info("Descobrindo pasta mais recente...")
        try:
            async with session.request("PROPFIND", url, auth=auth, headers=headers) as resp:
                if resp.status not in [200, 207]:
                    logger.warning(f"Falha ao listar pastas: Status {resp.status}")
                    return "2026-03"  # Fallback

                xml_content = await resp.text()
                root = ET.fromstring(xml_content)
                ns = {'d': 'DAV:'}
                folders = []
                
                for response in root.findall('.//d:response', ns):
                    href = response.find('d:href', ns).text
                    # Procura por pastas no formato YYYY-MM
                    if '/' in href:
                        folder_name = href.rstrip('/').split('/')[-1]
                        # Valida formato YYYY-MM
                        if len(folder_name) == 7 and folder_name[4] == '-':
                            try:
                                year = int(folder_name[:4])
                                month = int(folder_name[5:7])
                                if 2020 <= year <= 2030 and 1 <= month <= 12:
                                    folders.append(folder_name)
                            except ValueError:
                                continue

                if folders:
                    # Ordena e pega a mais recente
                    latest = sorted(folders)[-1]
                    logger.info(f"Pasta mais recente encontrada: {latest}")
                    return latest
                else:
                    logger.warning("Nenhuma pasta YYYY-MM encontrada, usando fallback")
                    return "2026-03"

        except Exception as e:
            logger.error(f"Erro ao descobrir pasta mais recente: {e}")
            return "2026-03"  # Fallback

    async def _is_valid_zip_header(self, file_path: Path) -> bool:
        if not file_path.exists() or file_path.stat().st_size < 4:
            return False
        with open(file_path, 'rb') as f:
            return f.read(4) == b'PK\x03\x04'

    async def _discover_via_propfind(self, session: aiohttp.ClientSession) -> List[str]:
        # Corrigido: track_duration só aceita a label 'stage'
        with metrics.track_duration(stage="discovery"):
            url = f"{self.webdav_base}/{self.target_dir}/"
            auth = aiohttp.BasicAuth(self.share_token, "")
            headers = {"Depth": "1"}

            logger.info(f"Listando arquivos em: {self.target_dir} via PROPFIND...")
            try:
                async with session.request("PROPFIND", url, auth=auth, headers=headers) as resp:
                    if resp.status not in [200, 207]:
                        logger.error(f"Falha ao listar pasta {self.target_dir}: Status {resp.status}")
                        # Corrigido: Usando método record_file que já trata as labels certas
                        metrics.record_file(stage="discovery", status="error")
                        return []

                    xml_content = await resp.text()
                    root = ET.fromstring(xml_content)
                    ns = {'d': 'DAV:'}
                    files = []
                    for response in root.findall('.//d:response', ns):
                        href = response.find('d:href', ns).text
                        if href.lower().endswith('.zip'):
                            filename = href.split('/')[-1]
                            files.append(filename)

                    metrics.record_file(stage="discovery", status="success")
                    logger.info(f"Encontrados {len(files)} arquivos para download")
                    return files

            except Exception as e:
                logger.error(f"Erro na descoberta via PROPFIND: {e}")
                metrics.record_file(stage="discovery", status="error")
                return []

    async def download_task(self, session: aiohttp.ClientSession, filename: str) -> Optional[Path]:
        async with self.semaphore:
            target_path = self.save_path / filename
            url = f"{self.webdav_base}/{self.target_dir}/{filename}"
            auth = aiohttp.BasicAuth(self.share_token, "")

            if target_path.exists() and await self._is_valid_zip_header(target_path):
                logger.info(f"Ja existe: {filename}")
                # 'skipped' é um status válido para o seu contador de arquivos
                metrics.record_file(stage="download", status="skipped")
                return target_path

            logger.info(f"Baixando: {filename}")

            # Corrigido: track_duration NÃO aceita labels extras como 'file'
            with metrics.track_duration(stage="download"):
                try:
                    async with session.get(url, auth=auth, timeout=self.timeout_seconds) as resp:
                        if resp.status != 200:
                            logger.error(f"Erro {resp.status} ao baixar {filename}")
                            metrics.record_file(stage="download", status="error")
                            return None

                        with open(target_path, "wb") as f:
                            async for chunk in resp.content.iter_chunked(1024 * 512):
                                f.write(chunk)

                    if await self._is_valid_zip_header(target_path):
                        # Registra sucesso e o volume em MB
                        file_size_mb = os.path.getsize(target_path) / (1024 * 1024)
                        metrics.record_file(stage="download", status="success")
                        metrics.record_volume(stage="download", size_mb=file_size_mb)
                        return target_path

                    metrics.record_file(stage="download", status="error")
                    target_path.unlink(missing_ok=True)
                    return None

                except Exception as e:
                    logger.error(f"Falha em {filename}: {e}")
                    metrics.record_file(stage="download", status="error")
                    return None

    async def extract(self) -> List[Path]:
        self.save_path.mkdir(parents=True, exist_ok=True)
        with metrics.track_duration(stage="pipeline_extraction"):
            async with aiohttp.ClientSession() as session:
                # Se RECEITA_TARGET_DIR não estiver no .env, descobre automaticamente
                if not os.getenv("RECEITA_TARGET_DIR"):
                    logger.info("RECEITA_TARGET_DIR não configurado, descobrindo automaticamente...")
                    self.target_dir = await self._discover_latest_folder(session)
                
                logger.info(f"Usando pasta: {self.target_dir}")
                
                file_list = await self._discover_via_propfind(session)

                if not file_list:
                    logger.warning("PROPFIND vazio. Usando fallback de nomes.")
                    file_list = ["CNAECNV.zip", "ESTABELE.zip", "EMPRE.zip", "SOCIO.zip"]
                    metrics.record_file(stage="discovery", status="fallback")

                tasks = [self.download_task(session, name) for name in file_list]
                results = await asyncio.gather(*tasks)
                successful = [f for f in results if isinstance(f, Path)]

                logger.info(f"Download concluido: {len(successful)}/{len(file_list)} baixados")
                return successful