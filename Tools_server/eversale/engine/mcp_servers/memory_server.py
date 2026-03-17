#!/usr/bin/env python3
"""
Memory MCP Server - Contact database and context management

Provides tools for:
- Saving contacts
- Searching contacts
- Logging interactions
- Retrieving history
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional


class MemoryServer:
    """MCP server for contact memory and context"""

    def __init__(self, db_path: str = "memory/contacts.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(exist_ok=True, parents=True)
        self._init_database()

    def _init_database(self):
        """Initialize SQLite database"""

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Contacts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                company TEXT,
                email TEXT,
                linkedin TEXT,
                title TEXT,
                context TEXT,
                status TEXT DEFAULT 'new',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Interactions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                content TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (contact_id) REFERENCES contacts(id)
            )
        """)

        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_contact_email ON contacts(email)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_contact_company ON contacts(company)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_interaction_contact ON interactions(contact_id)")

        conn.commit()
        conn.close()

    def save_contact(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Save a new contact"""

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO contacts (name, company, email, linkedin, title, context, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            params.get("name"),
            params.get("company"),
            params.get("email"),
            params.get("linkedin"),
            params.get("title"),
            params.get("context"),
            params.get("status", "new")
        ))

        contact_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return {
            "status": "success",
            "contact_id": contact_id,
            "message": f"Saved contact: {params.get('name')}"
        }

    def get_contact(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get a contact by ID or email"""

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = params.get("query")

        # Try by ID first
        if query.isdigit():
            cursor.execute("SELECT * FROM contacts WHERE id = ?", (int(query),))
        else:
            # Try by email or name
            cursor.execute("""
                SELECT * FROM contacts
                WHERE email = ? OR name LIKE ?
                LIMIT 1
            """, (query, f"%{query}%"))

        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        else:
            return {"error": "Contact not found"}

    def search_contacts(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Search contacts by criteria"""

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        conditions = []
        values = []

        if params.get("company"):
            conditions.append("company LIKE ?")
            values.append(f"%{params['company']}%")

        if params.get("status"):
            conditions.append("status = ?")
            values.append(params["status"])

        if params.get("name"):
            conditions.append("name LIKE ?")
            values.append(f"%{params['name']}%")

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        cursor.execute(f"""
            SELECT * FROM contacts
            WHERE {where_clause}
            ORDER BY updated_at DESC
            LIMIT 50
        """, values)

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def log_interaction(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Log an interaction with a contact"""

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO interactions (contact_id, type, content)
            VALUES (?, ?, ?)
        """, (
            params.get("contact_id"),
            params.get("type"),
            params.get("content")
        ))

        # Update contact's updated_at
        cursor.execute("""
            UPDATE contacts
            SET updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (params.get("contact_id"),))

        conn.commit()
        conn.close()

        return {
            "status": "success",
            "message": "Interaction logged"
        }

    def get_history(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get interaction history for a contact"""

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM interactions
            WHERE contact_id = ?
            ORDER BY timestamp DESC
        """, (params.get("contact_id"),))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def handle_tool_call(self, tool_name: str, params: Dict[str, Any]) -> Any:
        """Route tool calls to appropriate methods"""

        handlers = {
            "save_contact": self.save_contact,
            "get_contact": self.get_contact,
            "search_contacts": self.search_contacts,
            "log_interaction": self.log_interaction,
            "get_history": self.get_history,
        }

        if tool_name in handlers:
            return handlers[tool_name](params)
        else:
            return {"error": f"Unknown tool: {tool_name}"}


# MCP Protocol handler (simplified)
def main():
    """Run MCP server"""

    import sys

    server = MemoryServer()

    # Simple stdio-based MCP protocol
    for line in sys.stdin:
        try:
            request = json.loads(line)
            tool_name = request.get("tool")
            params = request.get("params", {})

            result = server.handle_tool_call(tool_name, params)

            response = {
                "status": "success",
                "result": result
            }

            print(json.dumps(response), flush=True)

        except Exception as e:
            error_response = {
                "status": "error",
                "error": str(e)
            }
            print(json.dumps(error_response), flush=True)


if __name__ == "__main__":
    main()
