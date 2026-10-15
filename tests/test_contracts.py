from __future__ import annotations

from pathlib import Path

import pytest

from followups.adapters.mock import (
    MockDeckGenerator,
    MockVideoGenerator,
    MockVisualGenerator,
)
from followups.domain.models import AssetBrief, Track
from tests.conftest import make_classification, make_prospect, make_reply

GENERATORS = [MockDeckGenerator, MockVideoGenerator, MockVisualGenerator]


def brief() -> AssetBrief:
    return AssetBrief(
        prospect=make_prospect(), reply=make_reply(), classification=make_classification()
    )


@pytest.mark.parametrize("gen_cls", GENERATORS)
def test_generator_declares_its_track(gen_cls):
    assert isinstance(gen_cls.track, Track)


@pytest.mark.parametrize("gen_cls", GENERATORS)
def test_generator_produces_a_previewable_asset(gen_cls, tmp_path):
    asset = gen_cls(tmp_path).generate(brief())
    assert asset.track is gen_cls.track
    assert asset.url
    assert Path(asset.preview_path).exists()


@pytest.mark.parametrize("gen_cls", GENERATORS)
def test_generator_output_is_deterministic(gen_cls, tmp_path):
    a = gen_cls(tmp_path).generate(brief())
    b = gen_cls(tmp_path).generate(brief())
    assert a.url == b.url


@pytest.mark.parametrize("gen_cls", GENERATORS)
def test_generator_personalises_with_the_company_name(gen_cls, tmp_path):
    asset = gen_cls(tmp_path).generate(brief())
    assert "Analytical Co" in Path(asset.preview_path).read_text()
