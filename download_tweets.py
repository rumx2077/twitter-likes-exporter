import json
import os
import re
from pathlib import Path

import httpx as requests

from build_site import build_site
from config import config
from merge_and_download import TweetMerger
from time_util import *
from tweet_parser import TweetParser

_logger = logging.getLogger(__name__)


class TweetDownloader:
    def __init__(self):
        self.backup_time_str = strfnow('UTC')
        self.header_authorization = config.get('header_authorization')
        self.header_cookie = config.get('header_cookies', '')

        # http client with retries (aligned with merge_and_download)
        proxy = os.environ.get("http_proxy") or os.environ.get("all_proxy")
        self._client = requests.Client(
            transport=requests.HTTPTransport(retries=3), timeout=30, proxy=proxy
        )

        # 从 cookie 中提取 CSRF token (ct0)
        csrf_match = re.findall('ct0=(.*?);', self.header_cookie)
        if not csrf_match:
            raise ValueError(
                "无法从 'header_cookies' 中找到 'ct0' (x-csrf-token)。请检查您的 config.yaml 文件。"
            )
        self.header_csrf = csrf_match[0]

        # 设置默认值
        self.incremental_backup = config.get("incremental_backup", True)
        self.max_sync_count = config.get("max_sync_count")

    def retrieve_all_likes(self):
        new_tweets = []
        stop_id = None
        output_file = config["output_json_path"]
        old_tweets = []

        # 增量备份时读取旧文件并设置stop_id
        if self.incremental_backup and output_file.exists():
            with open(output_file, "r", encoding="utf-8") as f:
                try:
                    loaded = json.load(f)
                    if loaded:
                        old_tweets = loaded["tweets"]
                        stop_id = old_tweets[0].get("tweet_id")
                except Exception:
                    old_tweets = []
                    stop_id = None

        # 非增量备份且文件存在，自动递增文件名
        if not self.incremental_backup and output_file.exists():
            parent_dir = output_file.parent
            name_toks = output_file.stem.split(".")
            num_tok = (
                len(name_toks) > 1
                and name_toks[-1].isnumeric()
                and name_toks[-1]
                or None
            )
            next_num = int(num_tok) if num_tok else 0
            base_name_toks = name_toks[:-1] if num_tok else name_toks
            while True:
                next_num += 1
                new_file = Path(
                    parent_dir,
                    ".".join(base_name_toks + [str(next_num)]) + output_file.suffix,
                )
                if not new_file.exists():
                    output_file = new_file
                    break

        likes_page = self.retrieve_likes_page()
        page_cursor = self.get_cursor(likes_page)
        old_page_cursor = None
        current_page = 1
        synced_count = 0

        while likes_page and page_cursor and page_cursor != old_page_cursor:
            _logger.info(
                f"Fetching likes page: {current_page}, {len(likes_page)} tweets fetched"
            )
            current_page += 1
            stop = False
            added_tweets_count = 0
            for raw_tweet in likes_page:
                if self.max_sync_count and synced_count >= self.max_sync_count:
                    stop = True
                    break
                try:
                    tweet_parser = TweetParser(raw_tweet, timezone=config["timezone"])
                    if tweet_parser.data_type != "tweet":
                        if tweet_parser.data_type == "unknown_type":
                            _logger.error(
                                f"raw_tweet 类型未知：{json.dumps(raw_tweet, ensure_ascii=False, indent=2)}"
                            )
                        continue
                    # 用stop_id判断增量终止
                    if stop_id and tweet_parser.tweet_id == str(stop_id):
                        stop = True
                        break
                    tweet_json = tweet_parser.tweet_as_json()

                    new_tweets.append(tweet_json)
                    added_tweets_count += 1
                    synced_count += 1
                except KeyError:
                    _logger.error(
                        f"raw_tweet json解析失败：{json.dumps(raw_tweet, ensure_ascii=False, indent=2)}"
                    )
            _logger.info(
                f"Added {added_tweets_count} new tweets, total {synced_count} tweets"
            )
            if stop:
                break
            old_page_cursor = page_cursor
            likes_page = self.retrieve_likes_page(cursor=page_cursor)
            page_cursor = self.get_cursor(likes_page)

        # 只在有新推时写入
        if new_tweets:
            all_tweets = new_tweets + old_tweets
            backup_data = {
                "backup_time": self.backup_time_str,
                "tweet_count": len(all_tweets),
                "page_cursor": page_cursor,
                "tweets": all_tweets,
            }
            with open(output_file, 'w', encoding="utf-8") as f:
                f.write(json.dumps(backup_data, ensure_ascii=False, indent=2))
            _logger.info(
                f'Done. JSON with {len(all_tweets)} liked tweets saved to: {output_file}'
            )
        else:
            _logger.info("No new tweets found")

    def retrieve_likes_page(self, cursor=None):
        likes_url = 'https://api.x.com/graphql/PW3fGqNrX-KazLPuqYA8lg/Likes'
        # likes_url = 'https://x.com/i/api/graphql/-ejCGuXo_HSdL8fBSPGSkA/Likes'
        variables_data_encoded = json.dumps(
            self.likes_request_variables_data(cursor=cursor)
        )
        features_data_encoded = json.dumps(self.likes_request_features_data())
        params = {
            "variables": variables_data_encoded,
            "features": features_data_encoded,
        }
        headers = self.likes_request_headers()
        response = self._client.get(
            likes_url,
            params=params,
            headers=headers,
        )
        return self.extract_likes_entries(response.json())

    def extract_likes_entries(self, raw_data):
        return raw_data['data']['user']['result']['timeline']['timeline'][
            'instructions'
        ][0]['entries']
        # return raw_data['data']['user']['result']['timeline_v2']['timeline'][
        #     'instructions'
        # ][0]['entries']

    def get_cursor(self, page_json):
        return page_json[-1]['content']['value']

    def likes_request_variables_data(self, cursor=None):
        variables_data = {
            "userId": config["user_id"],
            "count": 100,
            "cursor": cursor,
            "includePromotedContent": False,
            "withSuperFollowsUserFields": False,
            "withDownvotePerspective": False,
            "withReactionsMetadata": False,
            "withReactionsPerspective": False,
            "withSuperFollowsTweetFields": False,
            "withClientEventToken": False,
            "withBirdwatchNotes": False,
            "withVoice": False,
            "withV2Timeline": True,
        }

        # variables_data = {
        #     "userId": "",
        #     "count": 20,
        #     "includePromotedContent": False,
        #     "withClientEventToken": False,
        #     "withBirdwatchNotes": False,
        #     "withVoice": True,
        # }

        return variables_data

    def likes_request_headers(self):
        return {
            'Accept': '*/*',
            # 'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7',
            'Authorization': self.header_authorization,
            'Connection': 'keep-alive',
            'Content-Type': 'application/json',
            'Cookie': self.header_cookie,
            # 'Host': 'api.x.com',
            # 'Origin': 'https://x.com',
            # 'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Safari/605.1.15',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36',
            'Referer': 'https://x.com/',
            'x-csrf-token': self.header_csrf,
            'x-twitter-active-user': 'yes',
            # 'x-twitter-client-language': 'en',
            'x-twitter-auth-type': 'OAuth2Session',
            'x-twitter-client-language': 'zh-cn',
        }

    def likes_request_features_data(self):
        return {
            "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
            "interactive_text_enabled": True,
            "longform_notetweets_consumption_enabled": True,
            "responsive_web_edit_tweet_api_enabled": True,
            "responsive_web_enhance_cards_enabled": True,
            "responsive_web_graphql_exclude_directive_enabled": True,
            "responsive_web_graphql_timeline_navigation_enabled": True,
            "responsive_web_text_conversations_enabled": True,
            "responsive_web_twitter_blue_verified_badge_is_enabled": True,
            "responsive_web_uc_gql_enabled": True,
            "standardized_nudges_misinfo": True,
            "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
            "tweetypie_unmention_optimization_enabled": True,
            "verified_phone_label_enabled": True,
            "vibe_api_enabled": True,
            "view_counts_everywhere_api_enabled": True,
            "view_counts_public_visibility_enabled": True,
            # new features
            "articles_preview_enabled": True,
            "c9s_tweet_anatomy_moderator_badge_enabled": True,
            "communities_web_enable_tweet_community_results_fetch": True,
            "creator_subscriptions_quote_tweet_preview_enabled": False,
            "creator_subscriptions_tweet_preview_api_enabled": True,
            "freedom_of_speech_not_reach_fetch_enabled": True,
            "longform_notetweets_inline_media_enabled": True,
            "longform_notetweets_rich_text_read_enabled": True,
            "premium_content_api_read_enabled": False,
            "profile_label_improvements_pcf_label_in_post_enabled": True,
            "responsive_web_grok_analysis_button_from_backend": False,
            "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
            "responsive_web_grok_analyze_post_followups_enabled": True,
            "responsive_web_grok_image_annotation_enabled": True,
            "responsive_web_grok_share_attachment_enabled": True,
            "responsive_web_grok_show_grok_translated_post": False,
            "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
            "responsive_web_jetfuel_frame": False,
            "responsive_web_twitter_article_tweet_consumption_enabled": True,
            "rweb_tipjar_consumption_enabled": True,
            "rweb_video_screen_enabled": False,
            "tweet_awards_web_tipping_enabled": False,
        }

        # return {
        #     "rweb_video_screen_enabled": False,
        #     "payments_enabled": False,
        #     "profile_label_improvements_pcf_label_in_post_enabled": True,
        #     "rweb_tipjar_consumption_enabled": True,
        #     "verified_phone_label_enabled": False,
        #     "creator_subscriptions_tweet_preview_api_enabled": True,
        #     "responsive_web_graphql_timeline_navigation_enabled": True,
        #     "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
        #     "premium_content_api_read_enabled": False,
        #     "communities_web_enable_tweet_community_results_fetch": True,
        #     "c9s_tweet_anatomy_moderator_badge_enabled": True,
        #     "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
        #     "responsive_web_grok_analyze_post_followups_enabled": True,
        #     "responsive_web_jetfuel_frame": True,
        #     "responsive_web_grok_share_attachment_enabled": True,
        #     "articles_preview_enabled": True,
        #     "responsive_web_edit_tweet_api_enabled": True,
        #     "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
        #     "view_counts_everywhere_api_enabled": True,
        #     "longform_notetweets_consumption_enabled": True,
        #     "responsive_web_twitter_article_tweet_consumption_enabled": True,
        #     "tweet_awards_web_tipping_enabled": False,
        #     "responsive_web_grok_show_grok_translated_post": False,
        #     "responsive_web_grok_analysis_button_from_backend": False,
        #     "creator_subscriptions_quote_tweet_preview_enabled": False,
        #     "freedom_of_speech_not_reach_fetch_enabled": True,
        #     "standardized_nudges_misinfo": True,
        #     "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
        #     "longform_notetweets_rich_text_read_enabled": True,
        #     "longform_notetweets_inline_media_enabled": True,
        #     "responsive_web_grok_image_annotation_enabled": True,
        #     "responsive_web_grok_imagine_annotation_enabled": True,
        #     "responsive_web_grok_community_note_auto_translation_is_enabled": False,
        #     "responsive_web_enhance_cards_enabled": False,
        # }


if __name__ == '__main__':
    _logger.info(f'Starting retrieval of likes for Twitter user {config["user_id"]}...')
    TweetDownloader().retrieve_all_likes()
    TweetMerger().merge_and_save()
    build_site()
