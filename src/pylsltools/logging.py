import logging
from logging.handlers import QueueListener
import multiprocessing as mp
from logging.handlers import QueueHandler

def init_logging(level=logging.WARNING):
    logger = logging.getLogger("pylsltools")
    logger.setLevel(level)
    log_queue = mp.Queue()
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(levelname)s: %(name)s: %(processName)s: %(message)s")
    )
    log_listener = QueueListener(log_queue, handler)
    logger.addHandler(QueueHandler(log_queue))
    log_listener.start()
    return log_queue, log_listener


def init_sub_process_logging(queue, level=logging.WARNING):
    handler = logging.handlers.QueueHandler(queue)
    logger = logging.getLogger("pylsltools")
    logger.addHandler(handler)
