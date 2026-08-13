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

from sra_delivery.repository import DeliveryRepository

from .presenters import format_skill_response
from .repositories import InventoryRepository
from .skills import (
    GetStockSkill,
    GetTotalStockSkill,
    RequestDeliverySkill,
    SkillRegistry,
)


DB_CONFIG = {
    "host": os.getenv("SRA_V2_DB_HOST", "localhost"),
    "dbname": os.getenv("SRA_V2_DB_NAME", "sra_v2_db"),
    "user": os.getenv("SRA_V2_DB_USER", "sra_user"),
    "password": os.getenv("SRA_V2_DB_PASSWORD", ""),
    "port": int(os.getenv("SRA_V2_DB_PORT", "5432")),
}

OLLAMA_URL = os.getenv("SRA_OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.getenv("SRA_OLLAMA_MODEL", "llama3.1:8b-instruct-q4_K_M")


class AgentNode(Node):
    """Route operator requests through deterministic registered skills."""

    def __init__(self):
        super().__init__("sra_agent")

        self._connection = psycopg2.connect(**DB_CONFIG)
        self._connection.autocommit = False

        self.tts_pub = self.create_publisher(String, "/sra/tts/speak", 10)
        self.result_pub = self.create_publisher(String, "/sra/agent/result", 10)
        self.robot_job_pub = self.create_publisher(
            String,
            "/sra/robot/jobs/request",
            50,
        )

        inventory_repository = InventoryRepository(self._connection)
        delivery_repository = DeliveryRepository(self._connection)

        self.registry = SkillRegistry(
            [
                GetTotalStockSkill(inventory_repository),
                GetStockSkill(inventory_repository),
                RequestDeliverySkill(
                    delivery_repository,
                    self._publish_robot_job,
                ),
            ]
        )

        self.create_subscription(
            String,
            "/sra/operator/raw_command",
            self._command_callback,
            10,
        )

        self.get_logger().info(
            "Skill-based agent ready with %d registered skills."
            % len(self.registry.definitions())
        )

    def _command_callback(self, msg: String) -> None:
        request = self._select_skill(msg.data.strip())
        skill_name = request.get("skill")
        arguments = request.get("arguments", {})

        if not skill_name:
            response = (
                "No entendí con suficiente claridad la solicitud. Por favor, repítala."
            )
            self._publish_result(
                {
                    "skill": None,
                    "arguments": arguments,
                    "result": {
                        "success": False,
                        "error": "NO_MATCHING_SKILL",
                    },
                    "response": response,
                }
            )
            self._publish_response(response)
            return

        result = self.registry.execute(skill_name, arguments)
        response = format_skill_response(skill_name, result)

        self._publish_result(
            {
                "skill": skill_name,
                "arguments": arguments,
                "result": result,
                "response": response,
            }
        )
        self._publish_response(response)

    def _select_skill(self, text: str) -> dict[str, Any]:
        """Use the LLM only for skill selection and argument extraction."""
        definitions = json.dumps(self.registry.definitions(), ensure_ascii=False)
        system_prompt = f"""
You are the routing component of an industrial robot assistant.
Select exactly one available backend skill and extract only its arguments.
Never answer the operator's question yourself. Never write SQL. Never invent
backend results. If no skill applies, set skill to null.

Canonical backend values are English even when the operator speaks Spanish.
For fuse-box arguments, use only enum values declared by the selected skill.
Use inventory.get_total_stock when the operator asks for overall/total available
stock and does not specify a fuse-box configuration.
Use inventory.get_stock only when an exact bottom cover, top cover, and fuse
configuration are requested.

AVAILABLE SKILLS:
{definitions}

Return only JSON with this schema:
{{
  "skill": "skill.name" or null,
  "arguments": {{}}
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
            if not isinstance(parsed.get("arguments", {}), dict):
                parsed["arguments"] = {}
            return parsed
        except Exception as exc:
            self.get_logger().error(f"Skill selection failed: {exc}")
            return {"skill": None, "arguments": {}}

    def _publish_robot_job(self, payload: dict[str, Any]) -> None:
        msg = String()
        msg.data = json.dumps(payload)
        self.robot_job_pub.publish(msg)

    def _publish_result(self, payload: dict[str, Any]) -> None:
        msg = String()
        msg.data = json.dumps(payload, ensure_ascii=False)
        self.result_pub.publish(msg)

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
