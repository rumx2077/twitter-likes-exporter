import logging
import logging.config
from pathlib import Path

import httpx
from ruamel.yaml import YAML

yaml = YAML()
yaml.preserve_quotes = True  # 保留引号风格
with open("config.yaml", encoding="utf-8") as config_file:
    config = yaml.load(config_file)

config.setdefault("user_id", "")

config["site_path"] = Path(
    config.get("sites_path", "sites"), config.get("site_name", "liked_tweets")
)
config["site_path"].mkdir(parents=True, exist_ok=True)

config["output_json_path"] = config["site_path"] / config.get(
    "output_json_filename", "liked_tweets.json"
)

config["merged_json_path"] = (
    config["site_path"] / f"{config["output_json_path"].stem}_merged.json"
)

config["log_path"] = Path(config["site_path"], config.get("log", "liked_tweets.log"))

config.setdefault("enable_media_download", True)
config.setdefault("items_per_page", 500)


dict_config = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "{asctime} [{levelname}] {name}: {message}",
            "style": "{",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "level": "INFO",
            "stream": "ext://sys.stderr",
        },
        "file": {
            "class": "logging.FileHandler",
            "formatter": "standard",
            "level": "DEBUG",
            "filename": config["log_path"],
            "encoding": "utf8",
        },
    },
    "loggers": {
        "httpx": {
            "handlers": ["file"],
            "level": "DEBUG",
            "propagate": False,  # 防止日志消息向上传递给 root logger 导致重复记录
        }
    },
    "root": {"handlers": ["console", "file"], "level": "DEBUG"},
}
Path(config["log_path"]).parent.mkdir(parents=True, exist_ok=True)
logging.config.dictConfig(dict_config)


if __name__ == "__main__":
    logger = logging.getLogger()

    logger.debug(
        "这是一个 DEBUG 消息。",
        extra={"file_extra": "此条仅文件可见", "console_extra": "此条仅控制台可见"},
    )
    logger.info(
        "这是一个 INFO 消息。",
        extra={"file_extra": "文件专属内容", "console_extra": "控制台专属内容"},
    )
    logger.warning(
        "这是一个 WARNING 消息。",
        extra={"formatted_frame_info": "来自 frame_info 的警告"},
    )

    try:
        1 / 0
    except ZeroDivisionError:
        logger.error(
            "发生了一个错误！", exc_info=True, extra={"exc_summary": "除零错误摘要"}
        )

    httpx.get("https://www.google.com")
