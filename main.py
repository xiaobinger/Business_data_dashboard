import sys
import os
import webbrowser
import threading
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import ensure_data_dir, APP_NAME
ensure_data_dir()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

HOST = "127.0.0.1"
PORT = 9527


def open_browser():
    url = f"http://{HOST}:{PORT}"
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()


def main():
    from api.routes import app

    logger.info(f"🚀 {APP_NAME} 启动中...")
    logger.info(f"📍 访问地址: http://{HOST}:{PORT}")

    open_browser()

    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
