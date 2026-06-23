import pytest
import yaml

import main


class TestMakeJob:
    def test_calls_fetch_and_upsert(self, mocker):
        mock_fetch = mocker.patch("main.fetcher.fetch", return_value={"close": 150.0})
        mock_upsert = mocker.patch("main.db.upsert")

        job = main.make_job("AAPL", ["close"])
        job()

        mock_fetch.assert_called_once_with("AAPL", ["close"])
        mock_upsert.assert_called_once_with("AAPL", {"close": 150.0})

    def test_job_name_includes_symbol(self):
        job = main.make_job("GOOGL", ["close"])
        assert "GOOGL" in job.__name__

    def test_exception_does_not_propagate(self, mocker):
        mocker.patch("main.fetcher.fetch", side_effect=Exception("boom"))
        mocker.patch("main.db.upsert")

        job = main.make_job("AAPL", ["close"])
        job()  # must not raise


class TestRunOnStartup:
    def _run_main(self, mocker, run_on_startup: bool):
        config = {
            "settings": {"run_on_startup": run_on_startup},
            "tickers": [
                {"symbol": "AAPL", "schedule": "0 16 * * 1-5", "fields": ["close"]},
                {"symbol": "GOOGL", "schedule": "0 9 * * 1-5", "fields": ["close"]},
            ],
        }
        mocker.patch("builtins.open", mocker.mock_open(read_data=yaml.dump(config)))
        mock_fetch = mocker.patch("main.fetcher.fetch", return_value={"close": 100.0})
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
        mock_fetch = mocker.patch("main.fetcher.fetch", return_value={"close": 100.0})
        mocker.patch("main.db.upsert")
        mocker.patch("main.db.ensure_schema")
        mock_scheduler = mocker.MagicMock()
        mocker.patch("main.BlockingScheduler", return_value=mock_scheduler)

        main.main()
        mock_fetch.assert_not_called()

    def test_scheduler_started(self, mocker):
        self._run_main(mocker, run_on_startup=False)
        # BlockingScheduler.start() must be called regardless of run_on_startup
        mock_scheduler = mocker.patch("main.BlockingScheduler").return_value
        main_config = {
            "settings": {"run_on_startup": False},
            "tickers": [{"symbol": "AAPL", "schedule": "0 16 * * 1-5", "fields": ["close"]}],
        }
        mocker.patch("builtins.open", mocker.mock_open(read_data=yaml.dump(main_config)))
        mocker.patch("main.fetcher.fetch", return_value={})
        mocker.patch("main.db.upsert")
        mocker.patch("main.db.ensure_schema")
        main.main()
        mock_scheduler.start.assert_called_once()
