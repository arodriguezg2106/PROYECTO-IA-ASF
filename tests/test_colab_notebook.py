import json
from pathlib import Path


def test_colab_notebook_is_synthetic_only_and_contains_no_real_data_commands():
    notebook = json.loads(
        Path("notebooks/evaluacion_sintetica_colab.ipynb").read_text(encoding="utf-8")
    )
    code = "\n".join(
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
        if cell["cell_type"] == "code"
    )
    assert "--synthetic-only" in code
    assert "qwen3.5:9b" in code
    assert "drive.mount" not in code
    assert ".docx" not in code
    assert ".xlsx" not in code
    assert "paired_evaluation_bank" not in code
    assert "selected_model" in code
