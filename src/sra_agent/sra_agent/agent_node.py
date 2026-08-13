#!/usr/bin/env python3
"""Skill-based conversational agent for the Smart Robot Assistant.

The language model is limited to selecting a registered skill and extracting
arguments. Database queries and business rules remain deterministic backend
code. Operator-facing responses are produced in Spanish.
"""

import json
import os
from typing import Any

import psycopg2
import requests
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from .presenters import format_skill_response
from .repositories import InventoryRepository
from .skills import GetStockSkill, GetTotalStockSkill, SkillRegistry


DB_CONFIG = {
    "host": os.getenv("SRA_DB_HOST", "localhost"),
    "dbname": os.getenv("SRA_DB_NAME", "sra_db"),
    "user": os.getenv("SRA_DB_USER", "sra_user"),
    "password": os.getenv("SRA_DB_PASSWORD", ""),
    "port": int(os.getenv("SRA_DB_PORT", "5432")),
}

OLLAMA_URL = os.getenv("SRA_OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.getenv("SRA_OLLAMA_MODEL", "llama3.1:8b-instruct-q4_K_M")
CONFIDENCE_THRESHOLD = float(os.getenv("SRA_CONFIDENCE_THRESHOLD", "0.75"))


class AgentNode(Node):
    """Route operator requests through deterministic registered skills."""

    def __init__(self):
        super().__init__("sra_agent")

        self._connection = psycopg2.connect(**DB_CONFIG)
        self._connection.autocommit = False
        inventory_repository = InventoryRepository(self._connection)

        self.registry = SkillRegistry(
            [
                GetTotalStockSkill(inventory_repository),
                GetStockSkill(inventory_repository),
            ]
        )

        self.create_subscription(
            String,
            "/sra/operator/raw_command",
            self._command_callback,
            10,
        )
        self.tts_pub = self.create_publisher(String, "/sra/tts/speak", 10)
        self.result_pub = self.create_publisher(String, "/sra/agent/result", 10)

        self.get_logger().info(
            "Skill-based agent ready with %d registered skills."
            % len(self.registry.definitions())
        )

    def _command_callback(self, msg: String) -> None:
        request = self._select_skill(msg.data.strip())
        skill_name = request.get("skill")
        confidence = request.get("confidence", 0.0)

        if not skill_name or confidence < CONFIDENCE_THRESHOLD:
            self._publish_response(
                "No entendí con suficiente claridad la solicitud. Por favor, repítala."
            )
            return

        result = self.registry.execute(skill_name, request.get("arguments", {}))
        response = format_skill_response(skill_name, result)

        payload = {
            "skill": skill_name,
            "arguments": request.get("arguments", {}),
            "confidence": confidence,
            "result": result,
            "response": response,
        }
        out = String()
        out.data = json.dumps(payload, ensure_ascii=False)
        self.result_pub.publish(out)
        self._publish_response(response)

    def _select_skill(self, text: str) -> dict[str, Any]:
        """Use the LLM only for skill selection and argument extraction."""
        definitions = json.dumps(self.registry.definitions(), ensure_ascii=False)
        system_prompt = f"""
You are the routing component of an industrial robot assistant.
Select exactly one available backend skill and extract only its arguments.
Never answer the operator's question yourself. Never write SQL. Never invent
backend results. If no skill applies, set skill to null.

AVAILABLE SKILLS:
{definitions}

Return only JSON with this schema:
{{
  "skill": "skill.name" or null,
  "arguments": {{}},
  "confidence": 0.0
}}
""".strip()

        try:
            response = requests.post(
                OLLAMA_URL,
                json={
                    "model": OLLAMA_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": text},
                    ],
                    "stream": False,
                },
                timeout=30,
            )
            response.raise_for_status()
            content = response.json()["message"]["content"].strip()
            start = content.find("{")
            end = content.rfind("}")
            if start < 0 or end < start:
                raise ValueError("No JSON object returned by language model")
            parsed = json.loads(content[start:end + 1])
            confidence = parsed.get("confidence", 0.0)
            if not isinstance(confidence, (int, float)):
                confidence = 0.0
            parsed["confidence"] = max(0.0, min(1.0, float(confidence)))
            if not isinstance(parsed.get("arguments", {}), dict):
                parsed["arguments"] = {}
            return parsed
        except Exception as exc:
            self.get_logger().error(f"Skill selection failed: {exc}")
            return {"skill": None, "arguments": {}, "confidence": 0.0}

    def _publish_response(self, text: str) -> None:
        msg = String()
        msg.data = text
        self.tts_pub.publish(msg)

    def destroy_node(self):
        if self._connection is not None:
            self._connection.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = AgentNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
