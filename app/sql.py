"""
SQL для хранения обработанных сообщений (dedup).
"""

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS processed_messages (
    source TEXT,
    msg_id INTEGER,
    channel TEXT,
    parsed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (channel, msg_id)
);
"""
