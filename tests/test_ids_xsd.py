from pathlib import Path
from unittest.mock import patch

import pytest

from src.translator.ids_parser import parse_ids, validate_ids_against_xsd
from src.translator.rule_generator import normalize_numeric_value

IDS_NS_DECL = (
    'xmlns:ids="http://standards.buildingsmart.org/IDS" '
    'xmlns:xs="http://www.w3.org/2001/XMLSchema"'
)

MINIMAL_XSD = """<?xml version="1.0" encoding="utf-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           targetNamespace="http://standards.buildingsmart.org/IDS"
           xmlns:ids="http://standards.buildingsmart.org/IDS"
           elementFormDefault="qualified">
  <xs:element name="ids">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="specifications" minOccurs="1" maxOccurs="1">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="specification" minOccurs="1" maxOccurs="unbounded">
                <xs:complexType>
                  <xs:sequence>
                    <xs:element name="applicability" minOccurs="0" maxOccurs="1">
                      <xs:complexType mixed="true">
                        <xs:sequence>
                          <xs:any minOccurs="0" maxOccurs="unbounded" processContents="lax"/>
                        </xs:sequence>
                      </xs:complexType>
                    </xs:element>
                    <xs:element name="requirements" minOccurs="0" maxOccurs="1">
                      <xs:complexType mixed="true">
                        <xs:sequence>
                          <xs:any minOccurs="0" maxOccurs="unbounded" processContents="lax"/>
                        </xs:sequence>
                      </xs:complexType>
                    </xs:element>
                  </xs:sequence>
                  <xs:attribute name="name" type="xs:string" use="optional"/>
                </xs:complexType>
              </xs:element>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
"""


def _write_ids(tmp_path: Path, body: str) -> Path:
    ids_file = tmp_path / "test.ids"
    ids_file.write_text(body, encoding="utf-8")
    return ids_file


def _write_xsd(tmp_path: Path) -> Path:
    xsd_file = tmp_path / "ids.xsd"
    xsd_file.write_text(MINIMAL_XSD, encoding="utf-8")
    return xsd_file


def test_valid_ids_passes_xsd(tmp_path: Path) -> None:
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<ids:ids {IDS_NS_DECL}>
  <ids:specifications>
    <ids:specification name="Valid Spec">
      <ids:requirements />
    </ids:specification>
  </ids:specifications>
</ids:ids>
"""
    ids_file = _write_ids(tmp_path, xml)
    xsd_file = _write_xsd(tmp_path)

    assert validate_ids_against_xsd(ids_file, xsd_file) == []


def test_invalid_ids_fails_xsd(tmp_path: Path) -> None:
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<ids:ids {IDS_NS_DECL}>
  <ids:wrongNode />
</ids:ids>
"""
    ids_file = _write_ids(tmp_path, xml)
    xsd_file = _write_xsd(tmp_path)

    with pytest.raises(ValueError, match="contra XSD"):
        validate_ids_against_xsd(ids_file, xsd_file)


def test_parse_ids_without_xsd_file_logs_warning(tmp_path: Path) -> None:
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<ids:ids {IDS_NS_DECL}>
  <ids:specifications>
    <ids:specification name="Sem XSD">
      <ids:applicability>
        <ids:entity>
          <ids:name><ids:simpleValue>IFCWALL</ids:simpleValue></ids:name>
        </ids:entity>
      </ids:applicability>
      <ids:requirements>
        <ids:property>
          <ids:propertySet><ids:simpleValue>Pset_WallCommon</ids:simpleValue></ids:propertySet>
          <ids:baseName><ids:simpleValue>ThermalTransmittance</ids:simpleValue></ids:baseName>
        </ids:property>
      </ids:requirements>
    </ids:specification>
  </ids:specifications>
</ids:ids>
"""
    ids_file = _write_ids(tmp_path, xml)
    missing_xsd = tmp_path / "missing.xsd"

    with patch("src.translator.ids_parser.IDS_XSD_PATH", missing_xsd), patch(
        "src.translator.ids_parser.logger.warning"
    ) as mock_warning:
        specs = parse_ids(str(ids_file))

    assert len(specs) == 1
    mock_warning.assert_called_once()


def test_normalize_numeric_value_mm_to_m() -> None:
    assert normalize_numeric_value("200 mm", "m") == pytest.approx(0.2)


def test_normalize_numeric_value_plain_float() -> None:
    assert normalize_numeric_value("2.48", "W/(m²·K)") == pytest.approx(2.48)
