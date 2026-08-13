from sra_agent.presenters.spanish import format_skill_response
from sra_agent.skills.delivery import RequestDeliverySkill


class FakeDeliveryRepository:
    def create_request(self, **kwargs):
        assert kwargs["bottom_cover"] == "red"
        assert kwargs["top_cover"] == "blue"
        assert kwargs["fuse_configuration"] == "both"
        assert kwargs["quantity"] == 2
        assert kwargs["destination"] == "station_a"
        return {
            "request_id": 17,
            "destination": "station_a",
            "items": [
                {"part_number": 1527, "slot_id": "S03", "job_id": "job-1"},
                {"part_number": 1539, "slot_id": "S08", "job_id": "job-2"},
            ],
        }


def test_delivery_skill_returns_concrete_parts_and_publishes_jobs():
    published = []
    skill = RequestDeliverySkill(FakeDeliveryRepository(), published.append)

    result = skill.execute(
        {
            "bottom_cover": "red",
            "top_cover": "blue",
            "fuse_configuration": "both",
            "quantity": 2,
            "destination": "station_a",
        }
    )

    assert result["success"] is True
    assert result["request_id"] == 17
    assert result["parts"] == [1527, 1539]
    assert [job["job_id"] for job in published] == ["job-1", "job-2"]
    assert all(job["job_type"] == "DELIVERY" for job in published)


def test_delivery_response_is_natural_spanish_without_backend_codes():
    text = format_skill_response(
        "delivery.request",
        {
            "success": True,
            "request_id": 17,
            "bottom_cover": "red",
            "top_cover": "blue",
            "fuse_configuration": "both",
            "quantity": 2,
            "destination": "station_a",
            "parts": [1527, 1539],
            "status": "queued",
        },
    )

    assert "cubierta inferior roja" in text
    assert "tapa superior azul" in text
    assert "ambos fusibles" in text
    assert "red-blue-both" not in text
    assert "station_a" not in text
