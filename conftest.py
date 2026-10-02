# Детерминизм тестов: фиксируем окружение ДО импорта приложения,
# чтобы не подхватить .env разработчика. База — во временной папке
# (файл + NullPool безопасны при нескольких event loop'ах у TestClient).
import os
import tempfile

_TMP_DIR = tempfile.mkdtemp(prefix="pokerbot-tests-")
_DB_PATH = (_TMP_DIR + "/test.db").replace(os.sep, "/")

os.environ["BOT_TOKEN"] = ""
os.environ["DEV_MODE"] = "1"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB_PATH}"

# Наличие conftest в корне также добавляет корень проекта в sys.path,
# поэтому тесты импортируют пакет `app` без установки.
