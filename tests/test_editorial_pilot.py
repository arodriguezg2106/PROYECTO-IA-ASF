import hashlib

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

from pilot_editorial_crf import run_pilot


def _doc(path,text):
    doc=Document(); normal=doc.styles["Normal"]; normal.font.name="Calibri"; normal.font.size=Pt(11)
    normal.paragraph_format.alignment=WD_ALIGN_PARAGRAPH.JUSTIFY
    doc.add_paragraph(text); doc.save(path)


def test_pilot_continues_and_preserves_inputs(tmp_path):
    source=tmp_path/"input"; output=tmp_path/"output"; source.mkdir()
    _doc(source/"a.docx","La entidad entregó la documentación.")
    _doc(source/"b.docx","Se solicitó el oficio y/o el contrato.")
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob("*.docx")}
    report=run_pilot(source,output)
    assert report["summary"]["documents"]==report["summary"]["completed"]==2
    assert report["summary"]["failed"]==0 and report["summary"]["hashes_unchanged"]==2
    assert len(report["validation_sample"])>=1
    assert all((output/item["outputs"][kind]).exists() for item in report["documents"] for kind in ("json","html","markdown","sarif"))
    assert (output/"dashboard.html").exists()
    assert before=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob("*.docx")}
    resumed=run_pilot(source,output,resume=True)
    assert all(item["resumed"] for item in resumed["documents"])


def test_pilot_selects_representative_sample(tmp_path):
    source=tmp_path/"input"; output=tmp_path/"output"; source.mkdir()
    for index,text in enumerate(("Texto breve.","La ASF revisó información. "*10,"La entidad utilizó y/o."),1):
        _doc(source/f"{index}.docx",text)
    report=run_pilot(source,output,sample_size=2)
    assert report["summary"]["documents"]==2
    assert len(report["selection"])==2
    assert {item["role"] for item in report["selection"]}=={"corto","extenso"}
