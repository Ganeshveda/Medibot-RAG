from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
import json
from typing import Any

import config

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


@dataclass
class SqlRagResult:
    query: str
    answer: str
    sources: list[dict[str, Any]]


class SqlRag:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    def _connect(self):
        return sqlite3.connect(str(self.db_path))

    def _execute(self, sql: str) -> list[tuple[Any, ...]]:
        logger.info("Executing SQL: %s", sql)
        conn = self._connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        conn.close()
        return rows

    def _schema_summary(self) -> str:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        conn.close()
        summary_lines = []
        for table_name, sql in tables:
            summary_lines.append(f"TABLE {table_name}: {sql}")
        return "\n".join(summary_lines)

    def is_analytical_question(self, question: str) -> bool:
        normalized = question.lower()
        analytics_keywords = [
            "how many",
            "count",
            "average",
            "sum",
            "total",
            "most",
            "highest",
            "lowest",
            "open",
            "pending",
            "approved",
            "resolved",
            "billing",
            "bill",
            "invoice",
            "claims",
            "tickets",
            "maintenance",
            "equipment",
            "department",
            "breakdown",
        ]
        return any(keyword in normalized for keyword in analytics_keywords)

    def generate_sql(self, question: str, role: str) -> str:
        if role not in config.SQL_RAG_ROLES:
            raise PermissionError("SQL RAG access denied for role: %s" % role)

        if not self.is_analytical_question(question):
            raise ValueError("Unable to classify analytical question for SQL RAG")

        if config.GROQ_API_KEY:
            try:
                return self._llm_translate_question_to_sql(question)
            except Exception as e:
                logger.warning("LLM SQL translation failed; falling back to rule-based SQL. %s", e)

        return self._rule_based_sql(question)

    def _rule_based_sql(self, question: str) -> str:
        normalized = question.lower()

        if any(keyword in normalized for keyword in ["claim", "billing", "bill", "invoice", "insurer"]):
            return self._billing_query(question)
        if any(keyword in normalized for keyword in ["equipment", "maintenance", "ticket", "fault"]):
            return self._maintenance_query(question)
        raise ValueError("Unable to classify analytical question for SQL RAG")

    def _llm_translate_question_to_sql(self, question: str) -> str:
        from groq import Groq  # type: ignore[import-not-found]

        schema = self._schema_summary()
        prompt = (
            "You are a SQL generation assistant for an SQLite database. "
            "Only output a single SQL query. Do not add explanation or markdown. "
            "If the question cannot be answered with SQL, respond with 'UNSUPPORTED'.\n\n"
            f"Database schema:\n{schema}\n\n"
            f"Question: {question}\n"
            "SQL:" 
        )

        client = Groq(api_key=config.GROQ_API_KEY)
        response = client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=[
                {"role": "system", "content": "You generate SQL for an SQLite database and nothing else."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=256,
        )
        raw_sql = response.choices[0].message.content
        sql = self._extract_sql(raw_sql)
        if not sql:
            raise ValueError("LLM did not return a valid SQL query")
        return sql

    def _extract_sql(self, text: str) -> str:
        cleaned = text.strip()
        fenced = re.search(r"```(?:sql)?\s*(.*?)```", cleaned, re.S | re.I)
        if fenced:
            cleaned = fenced.group(1).strip()

        match = re.search(r"(?i)(SELECT|WITH).*", cleaned, re.S)
        if not match:
            return ""
        return match.group(0).strip()

    def _billing_query(self, question: str) -> str:
        normalized = question.lower()

        if "total" in normalized and ("bill" in normalized or "billing" in normalized or "claim" in normalized):
            return "SELECT SUM(claimed_amount) AS total_claim_amount FROM claims"
        if "pending" in normalized:
            return "SELECT claim_id, patient_name, department, diagnosis_code, claimed_amount, status FROM claims WHERE status='pending' ORDER BY submitted_date DESC LIMIT 10"
        if "approved" in normalized:
            return "SELECT claim_id, patient_name, department, diagnosis_code, claimed_amount, approved_amount, status FROM claims WHERE status='approved' ORDER BY resolved_date DESC LIMIT 10"
        if "amount" in normalized and "average" in normalized:
            return "SELECT department, AVG(claimed_amount) AS avg_claim_amount FROM claims GROUP BY department ORDER BY avg_claim_amount DESC"
        return "SELECT claim_id, patient_name, department, diagnosis_code, insurer, claimed_amount, approved_amount, status, submitted_date, resolved_date FROM claims ORDER BY submitted_date DESC LIMIT 10"

    def _maintenance_query(self, question: str) -> str:
        if "in_progress" in question.lower() or "in progress" in question.lower():
            return "SELECT ticket_id, equipment_name, equipment_id, category, campus, issue_type, status, raised_by, raised_date FROM maintenance_tickets WHERE status='in_progress' ORDER BY raised_date DESC LIMIT 10"
        if "resolved" in question.lower():
            return "SELECT ticket_id, equipment_name, equipment_id, category, campus, issue_type, status, raised_by, raised_date, resolved_date FROM maintenance_tickets WHERE status='resolved' ORDER BY resolved_date DESC LIMIT 10"
        if "equipment" in question.lower() and "fault" in question.lower():
            return "SELECT ticket_id, equipment_name, equipment_id, category, campus, issue_type, fault_code, status FROM maintenance_tickets ORDER BY raised_date DESC LIMIT 10"
        return "SELECT ticket_id, equipment_name, equipment_id, category, campus, issue_type, status, raised_by, raised_date, resolved_date FROM maintenance_tickets ORDER BY raised_date DESC LIMIT 10"

    def execute_question(self, question: str, role: str) -> SqlRagResult:
        if role not in config.SQL_RAG_ROLES:
            raise PermissionError("SQL RAG access denied for role: %s" % role)

        sql = self.generate_sql(question=question, role=role)
        rows = self._execute(sql)
        row_dicts = [dict(row) for row in rows]
        answer = self._generate_answer(question=question, sql=sql, rows=row_dicts)
        sources = row_dicts
        return SqlRagResult(query=sql, answer=answer, sources=sources)

    def _generate_answer(self, question: str, sql: str, rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "No matching records were found for this query."

        normalized_question = question.lower()

        # Prefer explicit scalar answers for aggregate queries.
        if len(rows) == 1:
            first_row = rows[0]
            aggregate_candidates = [
                key
                for key, value in first_row.items()
                if isinstance(value, (int, float))
                and any(token in key.lower() for token in ["total", "sum", "count", "avg", "amount"])
            ]
            if aggregate_candidates:
                key = aggregate_candidates[0]
                value = first_row[key]
                pretty_key = key.replace("_", " ")

                if isinstance(value, float):
                    pretty_value = f"{value:,.2f}"
                else:
                    pretty_value = f"{value:,}"

                if any(token in normalized_question for token in ["bill", "billing", "claim", "amount", "invoice", "cost"]):
                    return f"Total billed amount is {pretty_value}."
                return f"{pretty_key.title()}: {pretty_value}."

        if config.GROQ_API_KEY:
            try:
                from groq import Groq  # type: ignore[import-not-found]

                client = Groq(api_key=config.GROQ_API_KEY)
                response = client.chat.completions.create(
                    model=config.LLM_MODEL,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You summarize SQLite query results for a medical operations assistant. "
                                "Use only the provided SQL, question, and rows. Be concise, accurate, and do not invent values."
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                f"Question: {question}\n"
                                f"SQL: {sql}\n"
                                f"Rows: {json.dumps(rows, default=str)}\n"
                                "Write a short natural-language answer based only on these rows."
                            ),
                        },
                    ],
                    temperature=0,
                    max_tokens=256,
                )
                content = response.choices[0].message.content or ""
                if content.strip():
                    return content.strip()
            except Exception as exc:
                logger.warning("LLM answer generation failed; falling back to templated response. %s", exc)

        if "pending" in question.lower():
            return f"Found {len(rows)} pending records. The most recent pending items are shown."
        if "approved" in question.lower():
            return f"Found {len(rows)} approved records. The most recent resolved items are shown."
        if "average" in question.lower():
            return "Calculated average claim amount by department."

        return f"Returned {len(rows)} rows for the requested analytical question."


def sql_rag_chain(question: str, role: str) -> SqlRagResult:
    return SqlRag(config.DB_PATH).execute_question(question=question, role=role)
