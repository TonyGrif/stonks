import pandas as pd
import pytest
import yaml

import main

_ROWS = [(pd.Timestamp("2026-06-23 16:00:00", tz="UTC"), {"close": 150.0})]


class TestMakeJob:
    def test_calls_fetch_and_upsert(self, mocker):
        mock_fetch = mocker.patch("main.fetcher.fetch", return_value=_ROWS)
        mock_upsert = mocker.patch("main.db.upsert")

        job = main.make_job("AAPL", ["close"], "1d", "1d")
        job()

        mock_fetch.assert_called_once_with("AAPL", ["close"], "1d", "1d")
        mock_upsert.assert_called_once_with("AAPL", _ROWS)

    def test_period_and_interval_forwarded(self, mocker):
        mock_fetch = mocker.patch("main.fetcher.fetch", return_value=_ROWS)
        mocker.patch("main.db.upsert")

        job = main.make_job("SPY", ["close"], "5d", "5m")
        job()

        mock_fetch.assert_called_once_with("SPY", ["close"], "5d", "5m")

    def test_job_name_includes_symbol(self):
        job = main.make_job("GOOGL", ["close"], "1d", "1d")
        assert "GOOGL" in job.__name__

    def test_exception_does_not_propagate(self, mocker):
        mocker.patch("main.fetcher.fetch", side_effect=Exception("boom"))
        mocker.patch("main.db.upsert")

        job = main.make_job("AAPL", ["close"], "1d", "1d")
        job()  # must not raise


class TestRunOnStartup:
    def _run_main(self, mocker, run_on_startup: bool):
        config = {
            "settings": {"run_on_startup": run_on_startup, "timezone": "UTC"},
            "tickers": [
                {"symbol": "AAPL", "schedule": "0 16 * * 1-5", "fields": ["close"],
                 "period": "1d", "interval": "1d"},
                {"symbol": "GOOGL", "schedule": "0 9 * * 1-5", "fields": ["close"],
                 "period": "1d", "interval": "1d"},
            ],
        }
        mocker.patch("builtins.open", mocker.mock_open(read_data=yaml.dump(config)))
        mock_fetch = mocker.patch("main.fetcher.fetch", return_value=_ROWS)
        mocker.patch("main.db.upsert")
        mocker.patch("main.db.ensure_schema")
        mock_scheduler = mocker.MagicMock()
        mocker.patch("main.BlockingScheduler", return_value=mock_scheduler)

        main.main()
        return mock_fetch

    def test_true_fetches_all_tickers_on_start(self, mocker):
        mock_fetch = self._run_main(mocker, run_on_startup=True)
        symbols = [call.args[0] for call in mock_fetch.call_args_list]
        assert symbols == ["AAPL", "GOOGL"]

    def test_false_does_not_fetch_on_start(self, mocker):
        mock_fetch = self._run_main(mocker, run_on_startup=False)
        mock_fetch.assert_not_called()

    def test_missing_settings_defaults_to_false(self, mocker):
        config = {
            "tickers": [{"symbol": "AAPL", "schedule": "0 16 * * 1-5", "fields": ["close"]}]
        }
        mocker.patch("builtins.open", mocker.mock_open(read_data=yaml.dump(config)))
        mock_fetch = mocker.patch("main.fetcher.fetch", return_value=_ROWS)
        mocker.patch("main.db.upsert")
        mocker.patch("main.db.ensure_schema")
        mock_scheduler = mocker.MagicMock()
        mocker.patch("main.BlockingScheduler", return_value=mock_scheduler)

        main.main()
        mock_fetch.assert_not_called()

    def test_timezone_passed_to_cron_trigger(self, mocker):
        config = {
            "settings": {"run_on_startup": False, "timezone": "America/New_York"},
            "tickers": [{"symbol": "AAPL", "schedule": "0 16 * * 1-5", "fields": ["close"],
                         "period": "1d", "interval": "1d"}],
        }
        mocker.patch("builtins.open", mocker.mock_open(read_data=yaml.dump(config)))
        mocker.patch("main.fetcher.fetch", return_value=_ROWS)
        mocker.patch("main.db.upsert")
        mocker.patch("main.db.ensure_schema")
        mock_cron = mocker.patch("main.CronTrigger.from_crontab")
        mocker.patch("main.BlockingScheduler").return_value

        main.main()
        mock_cron.assert_called_once_with("0 16 * * 1-5", timezone="America/New_York")

    def test_missing_timezone_defaults_to_utc(self, mocker):
        config = {
            "tickers": [{"symbol": "AAPL", "schedule": "0 16 * * 1-5", "fields": ["close"]}]
        }
        mocker.patch("builtins.open", mocker.mock_open(read_data=yaml.dump(config)))
        mocker.patch("main.fetcher.fetch", return_value=_ROWS)
        mocker.patch("main.db.upsert")
        mocker.patch("main.db.ensure_schema")
        mock_cron = mocker.patch("main.CronTrigger.from_crontab")
        mocker.patch("main.BlockingScheduler").return_value

        main.main()
        mock_cron.assert_called_once_with("0 16 * * 1-5", timezone="UTC")

    def test_missing_period_interval_defaults_to_1d(self, mocker):
        config = {
            "settings": {"run_on_startup": True},
            "tickers": [{"symbol": "AAPL", "schedule": "0 16 * * 1-5", "fields": ["close"]}],
        }
        mocker.patch("builtins.open", mocker.mock_open(read_data=yaml.dump(config)))
        mock_fetch = mocker.patch("main.fetcher.fetch", return_value=_ROWS)
        mocker.patch("main.db.upsert")
        mocker.patch("main.db.ensure_schema")
        mocker.patch("main.BlockingScheduler").return_value

        main.main()
        mock_fetch.assert_called_once_with("AAPL", ["close"], "1d", "1d")

    def test_scheduler_started(self, mocker):
        self._run_main(mocker, run_on_startup=False)
        mock_scheduler = mocker.patch("main.BlockingScheduler").return_value
        main_config = {
            "settings": {"run_on_startup": False},
            "tickers": [{"symbol": "AAPL", "schedule": "0 16 * * 1-5", "fields": ["close"],
                         "period": "1d", "interval": "1d"}],
        }
        mocker.patch("builtins.open", mocker.mock_open(read_data=yaml.dump(main_config)))
        mocker.patch("main.fetcher.fetch", return_value=_ROWS)
        mocker.patch("main.db.upsert")
        mocker.patch("main.db.ensure_schema")
        main.main()
        mock_scheduler.start.assert_called_once()
