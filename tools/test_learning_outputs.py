"""Test method-bound menus and source-bound video packets."""
import importlib.util, sys, unittest
from pathlib import Path
R = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Outputs(unittest.TestCase):
    def test_menu_method_version_and_unknown_nutrition(self):
        m = module("planner", R / "skills/nutrition-system/scripts/update_planner.py") if (R / "skills/nutrition-system/scripts/update_planner.py").is_file() else None
        if m is None:
            self.skipTest("planner 已移除：营养方案由 Agent 直接写出 JSON")
        value = {"schema": 1, "current_plan": {"version": "menu-1", "target_version": "target-1", "target": {"version": "target-1", "method": "user-selected-method"}, "meals": [{"name": "早餐", "foods": [{"name": "示例食物", "portion": "用户待校准份量", "macros": {"calories": None}}]}]}}
        m.validate(value)
        value["current_plan"]["target"]["version"] = "target-2"
        with self.assertRaises(ValueError):
            m.validate(value)

    def test_source_packet_must_match_video(self):
        sys.path.insert(0, str(R / "skills/video-learning/scripts"))
        import question_tools as q
        with self.assertRaises(ValueError):
            q.validate({"source_id": "douyin:123456"}, {"source_id": "douyin:654321", "segments": [{"start": 0, "end": 2, "text": "text"}]})


if __name__ == "__main__":
    unittest.main()
