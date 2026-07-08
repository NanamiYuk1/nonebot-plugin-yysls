from pydantic import BaseModel, Field
from typing import List, Set


class YyslsConfig(BaseModel):
    # ========== 公告推送配置 ==========
    # ✅ 修正：燕云十六声网易官网新闻页
    yysls_news_url: str = "https://www.yysls.cn/news/"
    yysls_news_base_url: str = "https://www.yysls.cn"
    yysls_check_interval: int = 30  # 公告检查间隔（分钟）
    yysls_subscribe_groups: Set[int] = Field(default_factory=set)  # 订阅的群号

    # ========== 兑换码配置 ==========
    yysls_cdkey_sources: List[str] = Field(
        default_factory=lambda: [
            "https://www.yysls.cn/news/",  # 官方新闻页
        ]
    )

    # ========== 商城提醒配置 ==========
    yysls_shop_remind_day: int = 1  # 每月几号提醒（默认 1 号）
    yysls_shop_remind_hour: int = 10  # 提醒时间（24 小时制）
    yysls_shop_items: List[str] = Field(
        default_factory=lambda: [
            "和鸣 - 地华商店每月限时兑换",
        ]
    )