"""無主控台版本仍可保留錯誤紀錄。"""
import logging
import sys
from logging.handlers import RotatingFileHandler

def configure_logging(data_dir):
    directory = data_dir / 'logs'
    directory.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(directory / '程式.log', maxBytes=2_000_000, backupCount=3, encoding='utf-8')
    logging.basicConfig(level=logging.INFO, handlers=[handler],force=True,
                        format='%(asctime)s %(levelname)s %(message)s')
    def report_exception(kind, value, traceback):
        logging.critical('程式發生未處理錯誤', exc_info=(kind, value, traceback))
    sys.excepthook = report_exception
