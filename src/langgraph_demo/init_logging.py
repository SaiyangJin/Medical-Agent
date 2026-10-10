import logging
from logging import INFO
from logging import DEBUG

logging.basicConfig(
    level=logging.ERROR  #大于等于INFO的日志都会输出
    ,format="[%(asctime)s][%(name)s-%(levelname)s]-%(message)s"
)

logger=logging.getLogger(__name__)