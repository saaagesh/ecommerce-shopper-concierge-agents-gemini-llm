import os

class Config:
    GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "AIzaSyDCyKEC8m-fZ-YaiMOS_qb4_207tShbZ4M")
    VECTOR_SEARCH_URL = "https://www.ac0.cloudadvocacyorg.joonix.net/api/query"
    APP_NAME = "shop_concierge_app"
    USER_ID = "user_1"

config = Config()
