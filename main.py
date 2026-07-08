import os

from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    app_env = os.getenv("APP_ENV", "development")
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))

    print(f"Starting app in {app_env} mode on {host}:{port}")


if __name__ == "__main__":
    main()
