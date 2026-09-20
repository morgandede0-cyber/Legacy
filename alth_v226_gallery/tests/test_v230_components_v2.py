from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_no_empty_embeds_field_left_in_runtime_python():
    offenders = []
    for path in (ROOT / "main.py", ROOT / "legacy_world_forge.py", ROOT / "tower_engine.py"):
        text = path.read_text(encoding="utf-8")
        if "embeds=[]" in text.replace(" ", ""):
            offenders.append(path.name)
    assert not offenders, f"embeds=[] encore présent dans: {offenders}"


def test_story_uses_v2_renderer_and_starts_at_chapter_one():
    text = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "await show_story_page(interaction, 1)" in text
    start = text.index("async def show_story_page")
    end = text.index("class StoryCarouselView", start)
    story = text[start:end]
    assert "await edit_v2_surface(" in story
    assert "edit_original_response(\n        embed=" not in story


def test_hub_layout_is_not_registered_as_persistent_view():
    text = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "bot.add_view(HubView())" not in text
