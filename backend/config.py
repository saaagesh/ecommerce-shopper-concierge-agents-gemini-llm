import os

class Config:
    GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "AIzaSyA3Jj-m8ih28GTvlte0-xb5CNGwTbRW5jY")
    VECTOR_SEARCH_URL = "https://www.ac0.cloudadvocacyorg.joonix.net/api/query"
    APP_NAME = "shop_concierge_app"
    USER_ID = "user_1"

config = Config()
