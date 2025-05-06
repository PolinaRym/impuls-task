import xml.etree.ElementTree as ET
import json
import os
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set


@dataclass
class Attribute:
    name: str
    type: str


@dataclass
class ClassRelation:
    name: str
    type: str = "class"
    min: str = "1"
    max: str = "1"


@dataclass
class UMLClass:
    name: str
    is_root: bool = False
    documentation: str = ""
    attributes: List[Attribute] = field(default_factory=list)
    relations: List[ClassRelation] = field(default_factory=list)


class ModelParser:
    """Класс для парсинга UML модели из XML"""

    @staticmethod
    def parse_classes(xml_root) -> Dict[str, UMLClass]:
        classes = {}
        for elem in xml_root:
            if elem.tag == "Class":
                cls = UMLClass(
                    name=elem.attrib["name"],
                    is_root=elem.attrib.get("isRoot", "false") == "true",
                    documentation=elem.attrib.get("documentation", "")
                )
                cls.attributes = [
                    Attribute(name=attr.attrib["name"], type=attr.attrib["type"])
                    for attr in elem.findall("Attribute")
                ]
                classes[cls.name] = cls
        return classes

    @staticmethod
    def process_aggregations(xml_root, classes: Dict[str, UMLClass]):
        for elem in xml_root:
            if elem.tag == "Aggregation":
                source = elem.attrib["source"]
                target = elem.attrib["target"]

                # Добавляем связь только в source класс (родительский)
                if source in classes:
                    classes[source].relations.append(
                        ClassRelation(
                            name=target,
                            min=elem.attrib["targetMultiplicity"],
                            max=elem.attrib["targetMultiplicity"]
                        )
                    )


class ArtifactGenerator:
    """Базовый класс для генерации артефактов"""

    @staticmethod
    def ensure_output_dir():
        if not os.path.exists("out"):
            os.makedirs("out")


class ConfigXmlGenerator(ArtifactGenerator):
    """Генератор config.xml"""

    @staticmethod
    def generate(classes: Dict[str, UMLClass]):
        ArtifactGenerator.ensure_output_dir()

        def build_xml_element(class_name: str, indent: int = 0, processed: Optional[Set[str]] = None) -> List[str]:
            if processed is None:
                processed = set()

            if class_name in processed:
                return []

            processed.add(class_name)

            cls = classes[class_name]
            indent_str = "    " * indent
            xml_lines = []

            xml_lines.append(f"{indent_str}<{cls.name}>")

            for attr in cls.attributes:
                xml_lines.append(f"{indent_str}    <{attr.name}>{attr.type}</{attr.name}>")

            for rel in cls.relations:
                if rel.type == "class":
                    xml_lines.extend(build_xml_element(rel.name, indent + 1, processed))

            xml_lines.append(f"{indent_str}</{cls.name}>")
            return xml_lines

        root_class = next((cls for cls in classes.values() if cls.is_root), None)
        if not root_class:
            raise ValueError("Root class not found in model")

        xml_lines = ['<?xml version="1.0" encoding="UTF-8"?>']
        xml_lines.extend(build_xml_element(root_class.name))

        with open("out/config.xml", "w", encoding="utf-8") as f:
            f.write("\n".join(xml_lines))


class MetaJsonGenerator(ArtifactGenerator):
    """Генератор meta.json"""

    @staticmethod
    def generate(classes: Dict[str, UMLClass]):
        ArtifactGenerator.ensure_output_dir()

        meta_data = []
        for cls in classes.values():
            class_entry = {
                "class": cls.name,
                "documentation": cls.documentation,
                "isRoot": cls.is_root,
                "parameters": [
                    {"name": attr.name, "type": attr.type}
                    for attr in cls.attributes
                ]
            }

            for rel in cls.relations:
                if rel.type == "class":
                    class_entry["parameters"].append({
                        "name": rel.name,
                        "type": "class"
                    })
                    class_entry["min"] = rel.min
                    class_entry["max"] = rel.max

            meta_data.append(class_entry)

        with open("out/meta.json", "w", encoding="utf-8") as f:
            json.dump(meta_data, f, indent=4, ensure_ascii=False)


class DeltaJsonGenerator(ArtifactGenerator):
    """Генератор delta.json"""

    @staticmethod
    def generate(config_path: str, patched_config_path: str):
        ArtifactGenerator.ensure_output_dir()

        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        with open(patched_config_path, 'r', encoding='utf-8') as f:
            patched_config = json.load(f)

        delta = {
            "additions": [
                {"key": k, "value": v}
                for k, v in patched_config.items()
                if k not in config
            ],
            "deletions": [
                k for k in config
                if k not in patched_config
            ],
            "updates": [
                {"key": k, "from": config[k], "to": patched_config[k]}
                for k in config
                if k in patched_config and config[k] != patched_config[k]
            ]
        }

        with open("out/delta.json", "w", encoding='utf-8') as f:
            json.dump(delta, f, indent=4)


class ResPatchedConfigGenerator(ArtifactGenerator):
    """Генератор res_patched_config.json"""

    @staticmethod
    def generate(config_path: str, delta_path: str):
        ArtifactGenerator.ensure_output_dir()

        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        with open(delta_path, 'r', encoding='utf-8') as f:
            delta = json.load(f)

        result = config.copy()

        # Apply deletions
        for key in delta["deletions"]:
            result.pop(key, None)

        # Apply additions
        for addition in delta["additions"]:
            result[addition["key"]] = addition["value"]

        # Apply updates
        for update in delta["updates"]:
            result[update["key"]] = update["to"]

        with open("out/res_patched_config.json", "w", encoding='utf-8') as f:
            json.dump(result, f, indent=4)


def main():
    try:
        # Парсим модель
        tree = ET.parse("input/impulse_test_input.xml")
        root = tree.getroot()

        classes = ModelParser.parse_classes(root)
        ModelParser.process_aggregations(root, classes)

        # Генерируем артефакты
        ConfigXmlGenerator.generate(classes)
        MetaJsonGenerator.generate(classes)
        DeltaJsonGenerator.generate("input/config.json", "input/patched_config.json")
        ResPatchedConfigGenerator.generate("input/config.json", "out/delta.json")

        print("Артефакты успешно сгенерированы в папку out/")
    except Exception as e:
        print(f"Ошибка: {str(e)}")


if __name__ == "__main__":
    main()