# -*- coding: utf-8 -*-
"""
===================================
A股自选股智能分析系统 - 新闻情报存储单元测试
===================================

职责：
1. 验证新闻情报的保存与去重逻辑
2. 验证无 URL 情况下的兜底去重键
"""

import os
import sqlite3
import tempfile
import unittest

from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy.exc import OperationalError

from src.config import Config
from src.storage import DatabaseManager, NewsIntel
from src.search_service import SearchResponse, SearchResult


def test_legacy_news_intel_table_gets_quarantine_columns(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "legacy_news_intel.db"
    connection = sqlite3.connect(db_path)
    connection.execute(
        "CREATE TABLE news_intel ("
        "id INTEGER PRIMARY KEY, code VARCHAR(10) NOT NULL, "
        "title VARCHAR(300) NOT NULL, url VARCHAR(1000) NOT NULL)"
    )
    connection.commit()
    connection.close()

    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    Config.reset_instance()
    DatabaseManager.reset_instance()
    try:
        DatabaseManager.get_instance()
        connection = sqlite3.connect(db_path)
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(news_intel)").fetchall()
        }
        connection.close()
    finally:
        DatabaseManager.reset_instance()

    assert {"quarantined_at", "quarantine_reason", "quarantine_batch"} <= columns


class NewsIntelStorageTestCase(unittest.TestCase):
    """新闻情报存储测试"""

    def setUp(self) -> None:
        """为每个用例初始化独立数据库"""
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "test_news_intel.db")
        os.environ["DATABASE_PATH"] = self._db_path

        # 重置配置与数据库单例，确保使用临时库
        Config._instance = None
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()

    def tearDown(self) -> None:
        """清理资源"""
        DatabaseManager.reset_instance()
        self._temp_dir.cleanup()

    def _build_response(self, results) -> SearchResponse:
        """构造 SearchResponse 快捷函数"""
        return SearchResponse(
            query="贵州茅台 最新消息",
            results=results,
            provider="Bocha",
            success=True,
        )

    def test_save_news_intel_with_url_dedup(self) -> None:
        """相同 URL 去重，仅保留一条记录"""
        result = SearchResult(
            title="茅台发布新产品",
            snippet="公司发布新品...",
            url="https://news.example.com/a",
            source="example.com",
            published_date="2025-01-02"
        )
        response = self._build_response([result])

        query_context = {
            "query_id": "task_001",
            "query_source": "bot",
            "requester_platform": "feishu",
            "requester_user_id": "u_123",
            "requester_user_name": "测试用户",
            "requester_chat_id": "c_456",
            "requester_message_id": "m_789",
            "requester_query": "/analyze 600519",
        }

        saved_first = self.db.save_news_intel(
            code="600519",
            name="贵州茅台",
            dimension="latest_news",
            query=response.query,
            response=response,
            query_context=query_context
        )
        saved_second = self.db.save_news_intel(
            code="600519",
            name="贵州茅台",
            dimension="latest_news",
            query=response.query,
            response=response,
            query_context=query_context
        )

        self.assertEqual(saved_first, 1)
        self.assertEqual(saved_second, 0)

        with self.db.get_session() as session:
            total = session.query(NewsIntel).count()
            row = session.query(NewsIntel).first()
        self.assertEqual(total, 1)
        if row is None:
            self.fail("未找到保存的新闻记录")
        self.assertEqual(row.query_id, "task_001")
        self.assertEqual(row.requester_user_name, "测试用户")

    def test_save_news_intel_without_url_fallback_key(self) -> None:
        """无 URL 时使用兜底键去重"""
        result = SearchResult(
            title="茅台业绩预告",
            snippet="业绩大幅增长...",
            url="",
            source="example.com",
            published_date="2025-01-03"
        )
        response = self._build_response([result])

        saved_first = self.db.save_news_intel(
            code="600519",
            name="贵州茅台",
            dimension="earnings",
            query=response.query,
            response=response
        )
        saved_second = self.db.save_news_intel(
            code="600519",
            name="贵州茅台",
            dimension="earnings",
            query=response.query,
            response=response
        )

        self.assertEqual(saved_first, 1)
        self.assertEqual(saved_second, 0)

        with self.db.get_session() as session:
            row = session.query(NewsIntel).first()
            if row is None:
                self.fail("未找到保存的新闻记录")
            self.assertTrue(row.url.startswith("no-url:"))

    def test_get_recent_news(self) -> None:
        """可按时间范围查询最新新闻"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result = SearchResult(
            title="茅台股价震荡",
            snippet="盘中波动较大...",
            url="https://news.example.com/b",
            source="example.com",
            published_date=now
        )
        response = self._build_response([result])

        self.db.save_news_intel(
            code="600519",
            name="贵州茅台",
            dimension="market_analysis",
            query=response.query,
            response=response
        )

        recent_news = self.db.get_recent_news(code="600519", days=7, limit=10)
        self.assertEqual(len(recent_news), 1)
        self.assertEqual(recent_news[0].title, "茅台股价震荡")

    def test_save_news_intel_retries_on_sqlite_locked_execute(self) -> None:
        result = SearchResult(
            title="茅台锁竞争重试",
            snippet="模拟 SQLite locked...",
            url="https://news.example.com/retry",
            source="example.com",
            published_date="2025-01-05",
        )
        response = self._build_response([result])

        first_session = self.db.get_session()
        second_session = self.db.get_session()
        stmt_exc = OperationalError(
            "COMMIT",
            None,
            sqlite3.OperationalError("database is locked"),
        )

        with patch.object(self.db, "get_session", side_effect=[first_session, second_session]):
            with patch.object(first_session, "execute", side_effect=stmt_exc):
                with patch("src.storage.time.sleep") as mock_sleep:
                    saved_count = self.db.save_news_intel(
                        code="600519",
                        name="贵州茅台",
                        dimension="latest_news",
                        query=response.query,
                        response=response,
                    )

        self.assertEqual(saved_count, 1)
        self.assertEqual(mock_sleep.call_count, 1)
        self.assertAlmostEqual(mock_sleep.call_args.args[0], self.db._sqlite_write_retry_base_delay, places=6)

        with self.db.get_session() as session:
            total = session.query(NewsIntel).count()
        self.assertEqual(total, 1)

    def test_quarantine_hides_searxng_rows_and_can_rollback(self) -> None:
        searxng_response = SearchResponse(
            query="证券ETF 新闻",
            results=[SearchResult(
                title="旧 SearXNG 结果",
                snippet="待隔离",
                url="https://example.com/searxng",
                source="example.com",
                published_date=datetime.now().strftime("%Y-%m-%d"),
            )],
            provider="SearXNG",
            success=True,
        )
        anspire_response = SearchResponse(
            query="证券ETF 新闻",
            results=[SearchResult(
                title="可信 Anspire 结果",
                snippet="保留",
                url="https://example.com/anspire",
                source="example.com",
                published_date=datetime.now().strftime("%Y-%m-%d"),
            )],
            provider="Anspire",
            success=True,
        )
        context = {"query_id": "task_quarantine"}
        self.db.save_news_intel("512880", "证券ETF国泰", "latest_news", "q", searxng_response, context)
        self.db.save_news_intel("512880", "证券ETF国泰", "latest_news", "q", anspire_response, context)

        count = self.db.quarantine_news_intel(
            provider="SearXNG",
            before=datetime.now() + timedelta(seconds=1),
            batch="test-batch",
            reason="test",
        )
        self.assertEqual(count, 1)
        visible = self.db.get_news_intel_by_query_id("task_quarantine")
        self.assertEqual([item.provider for item in visible], ["Anspire"])
        with self.db.get_session() as session:
            self.assertEqual(session.query(NewsIntel).count(), 2)

        rolled_back = self.db.rollback_news_intel_quarantine(batch="test-batch")
        self.assertEqual(rolled_back, 1)
        visible = self.db.get_news_intel_by_query_id("task_quarantine")
        self.assertEqual({item.provider for item in visible}, {"Anspire", "SearXNG"})

    def test_quarantined_row_cannot_be_rehabilitated_by_url_collision(self) -> None:
        shared_url = "https://example.com/shared-result"
        searxng_response = SearchResponse(
            query="证券ETF 新闻",
            results=[SearchResult(
                title="旧污染标题",
                snippet="旧污染摘要",
                url=shared_url,
                source="example.com",
                published_date=datetime.now().strftime("%Y-%m-%d"),
            )],
            provider="SearXNG",
            success=True,
        )
        trusted_response = SearchResponse(
            query="证券ETF 双查询",
            results=[SearchResult(
                title="新可信标题",
                snippet="新可信摘要",
                url=shared_url,
                source="example.com",
                published_date=datetime.now().strftime("%Y-%m-%d"),
            )],
            provider="Anspire",
            success=True,
        )
        self.db.save_news_intel("512880", "证券ETF国泰", "latest_news", "q", searxng_response)
        self.db.quarantine_news_intel(
            provider="SearXNG",
            before=datetime.now() + timedelta(seconds=1),
            batch="collision-batch",
            reason="test",
        )

        self.assertEqual(
            self.db.save_news_intel(
                "512880",
                "证券ETF国泰",
                "latest_news",
                "q2",
                trusted_response,
            ),
            0,
        )
        self.assertEqual(self.db.get_recent_news("512880"), [])
        with self.db.get_session() as session:
            row = session.query(NewsIntel).filter(NewsIntel.url == shared_url).one()
            self.assertEqual(row.provider, "SearXNG")
            self.assertEqual(row.title, "旧污染标题")
            self.assertEqual(row.quarantine_batch, "collision-batch")


if __name__ == "__main__":
    unittest.main()
