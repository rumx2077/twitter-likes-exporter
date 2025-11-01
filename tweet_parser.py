from urllib.parse import parse_qs, parse_qsl, urlencode, urlparse, urlunparse

from time_util import DateTimeFormat, convert_datetime_format


class TweetParser:
    def __init__(self, raw_tweet_json, from_keydata=False, timezone=None):
        self.data_type = "unkonwn_type"
        self._media = None
        self.quoted_tweet = None
        self.retweeted_tweet = None
        self.timezone = timezone

        if from_keydata:
            self.key_data = raw_tweet_json
        else:
            self.raw_tweet_json = raw_tweet_json
            if raw_tweet_json.get("content"):
                if (
                    raw_tweet_json["content"].get("__typename")
                    == "TimelineTimelineCursor"
                ):
                    self.data_type = "cursor"
                if raw_tweet_json["content"].get("itemContent"):
                    if raw_tweet_json["content"]["itemContent"].get(
                        "promotedMetadata"
                    ):  # exclude advertisement
                        self.data_type = "advertisement"
                    self.key_data = raw_tweet_json["content"]["itemContent"][
                        "tweet_results"
                    ]["result"]
                    if self.key_data.get("__typename") == "TweetWithVisibilityResults":
                        self.key_data = self.key_data["tweet"]
                    if self.key_data.get("legacy"):
                        self.data_type = "tweet"
            if self.data_type != "tweet":
                return

        # 处理引用推特
        quoted_status_result = self.key_data.get("quoted_status_result", {})
        # 兼容 TweetWithVisibilityResults 结构
        if isinstance(quoted_status_result, dict) and "result" in quoted_status_result:
            quoted_parser = None
            quoted_result = quoted_status_result["result"]
            if (
                quoted_result.get("__typename") == "TweetWithVisibilityResults"
                and "tweet" in quoted_result
            ):
                quoted_parser = TweetParser(quoted_result["tweet"], from_keydata=True)
            elif quoted_result.get("__typename") == "TweetTombstone":
                quoted_tweet_url = (
                    self.key_data["legacy"]
                    .get("quoted_status_permalink", {})
                    .get("expanded")
                )
                quoted_tweet_url_path = urlparse(quoted_tweet_url).path
                quoted_tweet_userame = quoted_tweet_url_path.split("/")[1]
                quoted_tweet_id = self.key_data["legacy"].get("quoted_status_id_str")
                quoted_tweet_tombstone_text = (
                    quoted_result.get("tombstone", {}).get("text", {}).get("text")
                )
                self.quoted_tweet = {
                    "tweet_id": quoted_tweet_id,
                    "user_id": None,
                    "user_name": quoted_tweet_userame,
                    "tombstone": quoted_tweet_tombstone_text,
                }
            else:
                quoted_parser = TweetParser(quoted_result, from_keydata=True)
            if quoted_parser and quoted_parser.data_type == "tweet":
                self.quoted_tweet = quoted_parser.tweet_as_json()

        # 处理转推推特
        legacy = self.key_data.get("legacy", {})
        retweeted_status_result = legacy.get("retweeted_status_result", {})
        if (
            isinstance(retweeted_status_result, dict)
            and "result" in retweeted_status_result
        ):
            retweeted_parser = TweetParser(
                retweeted_status_result["result"],
                from_keydata=True,
            )
            if retweeted_parser.data_type == "tweet":
                self.retweeted_tweet = retweeted_parser.tweet_as_json()

    def tweet_as_json(self):
        return {
            "tweet_id": self.tweet_id,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "user_nick": self.user_nick,
            "avatar": {"media_url": self.user_avatar_url},
            "tweet_content": self.tweet_content,
            "tweet_media": self.media,
            "tweet_created_at": self.tweet_created_at,
            "quoted_tweet": self.quoted_tweet,
            "retweeted_tweet": self.retweeted_tweet,
            "view_count": self.view_count,
            "favorite_count": self.favorite_count,
            "reply_count": self.reply_count,
            "retweet_count": self.retweet_count,
            "quote_count": self.quote_count,
            "in_reply_to_status_id": self.in_reply_to_status_id,
            "in_reply_to_screen_name": self.in_reply_to_screen_name,
        }

    @property
    def tweet_id(self):
        return self.key_data["legacy"]["id_str"]

    @property
    def tweet_content(self):
        # 优先 note_tweet 里的文本，get链方式
        note_text = (
            self.key_data.get("note_tweet", {})
            .get("note_tweet_results", {})
            .get("result", {})
            .get("text")
        )
        if note_text:
            return note_text
        return self.key_data["legacy"]["full_text"]

    @property
    def tweet_created_at(self):
        return convert_datetime_format(
            self.key_data["legacy"]["created_at"],
            to_format=DateTimeFormat.DISPLAY,
            target_tz="UTC",
        )

    @property
    def user_id(self):
        return self.key_data["legacy"]["user_id_str"]

    @property
    def user_name(self):
        return self.user_data["screen_name"]

    @property
    def user_nick(self):
        return self.user_data["name"]

    @property
    def user_avatar_url(self):
        return self.user_data["profile_image_url_https"]

    @property
    def user_data(self):
        return self.key_data["core"]["user_results"]["result"]["legacy"]

    @property
    def media(self):
        if self._media is None:
            self._media = []
            legacy = self.key_data["legacy"]
            # 优先 extended_entities
            entities = legacy.get("extended_entities") or legacy.get("entities", {})
            media_entries = entities.get("media", [])
            for entry in media_entries:
                media_url = None
                media_type = entry.get("type")
                if media_type == "photo":
                    url = urlparse(entry["media_url_https"])
                    query = parse_qs(url.query)
                    query["name"] = ["orig"]
                    media_url = url._replace(
                        query=urlencode(query, doseq=True)
                    ).geturl()
                elif media_type in ("video", "animated_gif"):
                    # 链式获取variants
                    variants = entry.get("video_info", {}).get("variants", [])
                    highest_bitrate = -1
                    for v in variants:
                        if v.get("content_type", "").startswith("video"):
                            bitrate = v.get("bitrate", -1)
                            if bitrate > highest_bitrate:
                                highest_bitrate = bitrate
                                media_url = v.get("url")
                            elif highest_bitrate == -1:
                                media_url = v.get("url")
                self._media.append({"type": media_type, "media_url": media_url})
        return self._media

    # 互动数据和回复信息属性
    @property
    def view_count(self):
        views = self.key_data.get("views", {})
        count = views.get("count")
        try:
            return int(count)
        except (TypeError, ValueError):
            return 0

    @property
    def favorite_count(self):
        return self.key_data["legacy"].get("favorite_count", 0)

    @property
    def reply_count(self):
        return self.key_data["legacy"].get("reply_count", 0)

    @property
    def retweet_count(self):
        return self.key_data["legacy"].get("retweet_count", 0)

    @property
    def quote_count(self):
        return self.key_data["legacy"].get("quote_count", 0)

    @property
    def in_reply_to_status_id(self):
        return self.key_data["legacy"].get("in_reply_to_status_id_str")

    @property
    def in_reply_to_screen_name(self):
        return self.key_data["legacy"].get("in_reply_to_screen_name")
