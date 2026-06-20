"""Basic SQL RAG tests for Phase 3."""

from pathlib import Path

from sql_rag import SqlRag
import config


def test_sql_rag_billing_access():
    sql_rag = SqlRag(config.DB_PATH)
    result = sql_rag.execute_question("Show me pending claims", "billing_executive")
    print("SQL:", result.query)
    print("Answer:", result.answer)
    print("Rows:", len(result.sources))


def test_sql_rag_admin_access():
    sql_rag = SqlRag(config.DB_PATH)
    result = sql_rag.execute_question("List all resolved equipment tickets", "admin")
    print("SQL:", result.query)
    print("Answer:", result.answer)
    print("Rows:", len(result.sources))


def test_sql_rag_denied():
    sql_rag = SqlRag(config.DB_PATH)
    try:
        sql_rag.execute_question("Show me pending claims", "doctor")
    except PermissionError as e:
        print("Permission denied as expected:", e)


if __name__ == "__main__":
    test_sql_rag_billing_access()
    test_sql_rag_admin_access()
    test_sql_rag_denied()
