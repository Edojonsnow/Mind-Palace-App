from sqlalchemy import text

from app.db.session import engine


def main() -> None:
    with engine.connect() as connection:
        value = connection.execute(text("select current_database(), current_user")).one()

    print(f"Connected to database={value[0]} as user={value[1]}")


if __name__ == "__main__":
    main()

