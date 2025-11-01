import json
import logging
import os
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from time import sleep
from urllib.parse import parse_qs, urlencode, urlparse

import httpx as requests
import networkx as nx

from build_site import build_site
from config import config
from time_util import (
    DateTimeFormat,
    convert_datetime_format,
    format_datetime,
    system_tz,
)

_logger = logging.getLogger(__name__)


class TweetMerger:
    def __init__(self):
        self.json_filename_base = config["output_json_path"].stem
        self.enable_media_download = config.get("enable_media_download", True)
        self.media_filename_pattern = config.get(
            "media_filename_pattern",
            "{user_name}_{datetime}_{media_type}{num}_tid{tweet_id}_uid{user_id}.{extension}",
        )

        self.graph = nx.DiGraph()

        proxy = os.environ.get("http_proxy") or os.environ.get("all_proxy")
        self._client = requests.Client(
            transport=requests.HTTPTransport(retries=3), timeout=1, proxy=proxy
        )

    def find_tweets_files(self):
        files = sorted(
            p
            for p in config["site_path"].glob(f"{self.json_filename_base}*.json")
            if p != config["merged_json_path"]
        )
        _logger.info(f"开始合并 {len(files)} 个文件: {[str(f) for f in files]}")
        return files

    def build_graph(self, tweet_files):
        """从 JSON 文件读取数据并构建DAG图。"""
        for file_path in tweet_files:
            _logger.info(f"正在处理文件: {file_path}")
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # 设置文件中数据的默认备份时间
                if backup_time := data.get("backup_time"):
                    backup_time = convert_datetime_format(backup_time, target_tz="UTC")
                else:
                    file_stat = file_path.stat()
                    if hasattr(file_stat, "st_birthtime"):
                        _logger.warning(
                            f"{file_path}: 备份时间缺失，使用文件创建时间为推特默认更新时间"
                        )
                        backup_timestamp = file_stat.st_birthtime
                    else:
                        _logger.warning(
                            f"{file_path}: 备份时间缺失且创建时间未知，使用文件修改时间"
                        )
                        backup_timestamp = file_stat.st_ctime

                    backup_time = format_datetime(
                        datetime.fromtimestamp(backup_timestamp), target_tz="UTC"
                    )

                tweets = data.get("tweets", [])

                previous_tweet_id = None
                # 创建DAG图
                for current_tweet in tweets:
                    current_tweet.setdefault(
                        "updated_at", current_tweet.pop("backup_time", backup_time)
                    )

                    cur_quote = current_tweet.get("quoted_tweet")
                    if cur_quote and (
                        cur_quote.get("tweet_type") == "TweetTombstone"
                        or not cur_quote["tweet_id"]
                    ):
                        cur_quote["tombstone"] = cur_quote.pop("tweet_content")
                        cur_quote.pop("tweet_type", None)

                    current_tweet_id = current_tweet["tweet_id"]
                    # 节点采用最新推文数据
                    if current_tweet_id not in self.graph:
                        self.graph.add_node(current_tweet_id, tweet=current_tweet)
                    else:
                        node_tweet = self.graph.nodes[current_tweet_id]["tweet"]
                        rival_tweet = current_tweet

                        # 保持 node_tweet 为较新版本
                        if rival_tweet["updated_at"] > node_tweet["updated_at"]:
                            self.graph.nodes[current_tweet_id]["tweet"] = rival_tweet
                            node_tweet, rival_tweet = rival_tweet, node_tweet

                        # 合并墓碑引文
                        node_quote = node_tweet.get("quoted_tweet")
                        rival_quote = rival_tweet.get("quoted_tweet")

                        if not node_quote:
                            if rival_quote:
                                node_tweet["quoted_tweet"] = rival_quote
                        elif (
                            "tombstone" in node_quote
                            and rival_quote
                            and "tweet_content" in rival_quote
                        ):
                            # 节点有墓碑信息，另一侧有完整引文，合并较新引文
                            node_q_updated = node_quote.get("updated_at", '0')
                            rival_q_updated = rival_quote.get(
                                "updated_at", rival_tweet["updated_at"]
                            )
                            if rival_q_updated > node_q_updated:
                                rival_quote |= {
                                    "updated_at": rival_q_updated,
                                    **(
                                        node_quote
                                        if node_quote.get("user_nick") is not None
                                        else {}
                                    ),
                                    "tombstone": node_quote["tombstone"],
                                    "tombstone_updated_at": node_tweet["updated_at"],
                                }
                                node_tweet["quoted_tweet"] = rival_quote

                    if previous_tweet_id:
                        self.graph.add_edge(previous_tweet_id, current_tweet_id)

                    previous_tweet_id = current_tweet_id

        TR = nx.transitive_reduction(self.graph)
        TR.add_nodes_from(self.graph.nodes(data=True))
        self.graph = TR

    def merge_and_save(self):
        tweet_files = self.find_tweets_files()
        if not tweet_files:
            _logger.info("未找到需要合并的文件。")
            return

        self.build_graph(tweet_files)

        _logger.info("正在拓扑排序...")
        sorted_nodes = list(nx.topological_sort(self.graph))

        sorted_tweets = []
        for node_id in sorted_nodes:
            # 从节点中取出推文数据
            sorted_tweets.append(self.graph.nodes[node_id]["tweet"])

        for i, tweet in enumerate(sorted_tweets):
            quote = tweet.get("quoted_tweet") or tweet.get("retweeted_tweet")
            for t in [tweet, quote]:
                if not t:
                    continue
                if "user_avatar_url" in t:
                    t["avatar"] = {"media_url": t.pop("user_avatar_url")}
                if media := t.get("tweet_media"):
                    for m in media:
                        if m["type"] == "photo":
                            url = urlparse(m["media_url"])
                            query = parse_qs(url.query)
                            query["name"] = ["orig"]
                            m["media_url"] = url._replace(
                                query=urlencode(query, doseq=True)
                            ).geturl()

            # 标注需要明确父节点的条目
            # 跳过首节点
            if i == 0:
                continue

            node_id = tweet["tweet_id"]

            # 获取简约图父节点
            parents = list(self.graph.predecessors(node_id))

            # 若拓扑排序前驱与父节点不一致，则记录父节点
            if [sorted_nodes[i - 1]] != parents:
                tweet["original_parents"] = parents
                _logger.info(f"已标记推特 {node_id} 的原始父节点: {parents}")

        output_data = {
            "tweet_count": len(sorted_tweets),
            "tweets": sorted_tweets,
        }

        _logger.info(
            f"{len(sorted_tweets)} 条推特已合并至 {config['merged_json_path']}"
        )
        self._write_merged(output_data)

        _logger.info("合并完成。")

        if self.enable_media_download:
            _logger.info("开始下载媒体...")
            for tweet in sorted_tweets:
                self.download_media(tweet)
            self._write_merged(output_data)
            _logger.info("媒体下载完毕")

    def download_media(self, tweet):
        if (avatar := tweet.get("avatar")) is None:
            # 没有头像说明是墓碑推文
            return

        media_list = [avatar, *tweet.get("tweet_media", [])]
        for idx, media_item in enumerate(media_list):
            url = media_item.get("media_url")
            if not url:
                continue
            if idx == 0:
                filename = f"avatar_@{tweet['user_name']}_{tweet['user_id']}.jpg"
            else:
                ext = url.split("?")[0].split(".")[-1]
                filename = self.media_filename_pattern.format(
                    user_nick=tweet.get("user_name", "user"),
                    datetime=convert_datetime_format(
                        tweet.get("tweet_created_at"),
                        to_format=DateTimeFormat.FILENAME,
                        target_tz=system_tz,
                    ),
                    media_type=media_item.get("type", "media"),
                    num=idx,
                    tweet_id=tweet.get("tweet_id", ""),
                    user_id=tweet.get("user_id", ""),
                    extension=ext,
                )
            media_local_path = Path(config["site_path"], "media", filename)
            success = self.download_file(url, media_local_path)
            if success:
                media_item["filename"] = filename

        if tweet.get("quoted_tweet"):
            self.download_media(tweet["quoted_tweet"])
        if tweet.get("retweeted_tweet"):
            self.download_media(tweet["retweeted_tweet"])

    def download_file(self, url, local_path):
        filename = local_path.name
        if local_path.exists():
            return True
        _logger.info(f"Downloading media {filename}...")
        try:
            resp = self._client.get(url)
            resp.raise_for_status()
            local_path.parent.mkdir(parents=True, exist_ok=True)
            with open(local_path, "wb") as f:
                f.write(resp.content)
            return True
        except Exception as e:
            _logger.error(f"文件下载失败。url:{url}, filename:{filename}, 原因：{e}")
            return False

    def _write_merged(self, output_data: dict):
        with open(config['merged_json_path'], "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2, default=str)


if __name__ == "__main__":
    TweetMerger().merge_and_save()
    build_site()
