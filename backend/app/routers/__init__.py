"""路由注册"""
from app.routers import auth, books, reading, wiki, analytics
routers = [auth.router, books.router, reading.router, wiki.router, analytics.router]
