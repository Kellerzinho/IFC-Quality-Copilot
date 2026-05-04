"""Registry central de entidades e categorias de dados IFC suportadas."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class IfcNamedResource:
    """Recurso IFC nomeado indexado por categoria de dado."""

    name: str
    category: str
    applies_to: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class IfcEntityDefinition:
    """Definição resumida de uma entidade IFC relevante para o projeto."""

    name: str
    categories: tuple[str, ...]
    default_psets: tuple[str, ...] = ()
    default_quantities: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    domains: tuple[str, ...] = ()


@dataclass
class IfcDataRegistry:
    """Lookup central para entidades e categorias de dados IFC."""

    entities: dict[str, IfcEntityDefinition] = field(default_factory=dict)
    properties: dict[str, IfcNamedResource] = field(default_factory=dict)
    psets: dict[str, IfcNamedResource] = field(default_factory=dict)
    quantities: dict[str, IfcNamedResource] = field(default_factory=dict)
    materials: dict[str, IfcNamedResource] = field(default_factory=dict)
    classifications: dict[str, IfcNamedResource] = field(default_factory=dict)
    relations: dict[str, IfcNamedResource] = field(default_factory=dict)
    boundaries: dict[str, IfcNamedResource] = field(default_factory=dict)
    _entity_aliases: dict[str, str] = field(default_factory=dict)

    def register_entity(self, definition: IfcEntityDefinition) -> None:
        self.entities[definition.name] = definition
        self._entity_aliases[self._norm(definition.name)] = definition.name
        for alias in definition.aliases:
            self._entity_aliases[self._norm(alias)] = definition.name

    def entity(self, name: str) -> IfcEntityDefinition | None:
        canonical = self._entity_aliases.get(self._norm(name))
        if canonical is None:
            return None
        return self.entities.get(canonical)

    def has_entity(self, name: str) -> bool:
        return self.entity(name) is not None

    def category_names(self) -> tuple[str, ...]:
        return (
            "entities",
            "properties",
            "psets",
            "quantities",
            "materials",
            "classifications",
            "relations",
            "boundaries",
        )

    def resources_for_entity(self, entity_name: str, category: str) -> list[str]:
        entity = self.entity(entity_name)
        if entity is None:
            return []

        source: dict[str, IfcNamedResource] = getattr(self, category)
        names: list[str] = []
        for resource in source.values():
            if not resource.applies_to or entity.name in resource.applies_to:
                names.append(resource.name)
        return names

    @staticmethod
    def _norm(value: str) -> str:
        return value.strip().casefold()


def create_default_ifc_data_registry() -> IfcDataRegistry:
    registry = IfcDataRegistry()

    for entity in [
        IfcEntityDefinition(
            name="IfcSite",
            categories=("spatial", "base_ifc"),
            aliases=("IFCSITE",),
            domains=("base_ifc", "compliance"),
        ),
        IfcEntityDefinition(
            name="IfcBuilding",
            categories=("spatial", "base_ifc"),
            aliases=("IFCBUILDING",),
            domains=("base_ifc", "fm", "compliance"),
        ),
        IfcEntityDefinition(
            name="IfcBuildingStorey",
            categories=("spatial", "base_ifc"),
            aliases=("IFCBUILDINGSTOREY",),
            domains=("base_ifc", "budget", "fm", "compliance"),
        ),
        IfcEntityDefinition(
            name="IfcSpace",
            categories=("spatial", "occupancy"),
            default_psets=("Pset_SpaceCommon",),
            default_quantities=("Qto_SpaceBaseQuantities",),
            aliases=("IFCSPACE",),
            domains=("base_ifc", "ids", "energy", "hvac", "fm", "compliance"),
        ),
        IfcEntityDefinition(
            name="IfcWall",
            categories=("element", "envelope"),
            default_psets=("Pset_WallCommon",),
            default_quantities=("Qto_WallBaseQuantities",),
            aliases=("IFCWALL", "IFCWALLSTANDARDCASE"),
            domains=("base_ifc", "ids", "budget", "energy", "compliance"),
        ),
        IfcEntityDefinition(
            name="IfcSlab",
            categories=("element", "envelope"),
            default_psets=("Pset_SlabCommon",),
            default_quantities=("Qto_SlabBaseQuantities",),
            aliases=("IFCSLAB",),
            domains=("base_ifc", "ids", "budget", "energy", "compliance"),
        ),
        IfcEntityDefinition(
            name="IfcFlowSegment",
            categories=("mep", "hvac"),
            aliases=("IFCFLOWSEGMENT",),
            domains=("base_ifc", "hvac", "fm"),
        ),
        IfcEntityDefinition(
            name="IfcFlowTerminal",
            categories=("mep", "hvac"),
            aliases=("IFCFLOWTERMINAL",),
            domains=("base_ifc", "hvac", "fm"),
        ),
        IfcEntityDefinition(
            name="IfcFlowFitting",
            categories=("mep", "hvac"),
            aliases=("IFCFLOWFITTING",),
            domains=("base_ifc", "hvac", "fm"),
        ),
        IfcEntityDefinition(
            name="IfcDistributionElement",
            categories=("mep",),
            aliases=("IFCDISTRIBUTIONELEMENT",),
            domains=("base_ifc", "hvac", "fm"),
        ),
        IfcEntityDefinition(
            name="IfcRelContainedInSpatialStructure",
            categories=("relation", "spatial"),
            aliases=("IFCRELCONTAINEDINSPATIALSTRUCTURE",),
            domains=("base_ifc", "fm", "compliance"),
        ),
        IfcEntityDefinition(
            name="IfcRelSpaceBoundary",
            categories=("relation", "boundary"),
            aliases=("IFCRELSPACEBOUNDARY",),
            domains=("base_ifc", "energy", "hvac", "compliance"),
        ),
        IfcEntityDefinition(
            name="IfcElementQuantity",
            categories=("quantity",),
            aliases=("IFCELEMENTQUANTITY",),
            domains=("base_ifc", "budget"),
        ),
    ]:
        registry.register_entity(entity)

    for resource in [
        IfcNamedResource("LongName", "property", ("IfcSpace",)),
        IfcNamedResource("Name", "property", ("IfcSpace", "IfcBuildingStorey", "IfcBuilding", "IfcSite")),
        IfcNamedResource("ThermalTransmittance", "property", ("IfcWall", "IfcSlab")),
        IfcNamedResource("IsExternal", "property", ("IfcWall", "IfcSlab")),
        IfcNamedResource("Category", "property", ("IfcSpace",)),
        IfcNamedResource("FireRating", "property", ("IfcWall", "IfcSlab")),
        IfcNamedResource("Reference", "property", ("IfcDistributionElement", "IfcFlowTerminal")),
    ]:
        registry.properties[resource.name] = resource

    for resource in [
        IfcNamedResource("Pset_SpaceCommon", "pset", ("IfcSpace",)),
        IfcNamedResource("Pset_WallCommon", "pset", ("IfcWall",)),
        IfcNamedResource("Pset_SlabCommon", "pset", ("IfcSlab",)),
    ]:
        registry.psets[resource.name] = resource

    for resource in [
        IfcNamedResource("Qto_SpaceBaseQuantities", "quantity", ("IfcSpace",)),
        IfcNamedResource("Qto_WallBaseQuantities", "quantity", ("IfcWall",)),
        IfcNamedResource("Qto_SlabBaseQuantities", "quantity", ("IfcSlab",)),
        IfcNamedResource("NetFloorArea", "quantity", ("IfcSpace",)),
        IfcNamedResource("GrossFloorArea", "quantity", ("IfcSpace",)),
        IfcNamedResource("NetSideArea", "quantity", ("IfcWall",)),
        IfcNamedResource("NetArea", "quantity", ("IfcSlab",)),
        IfcNamedResource("Volume", "quantity", ("IfcWall", "IfcSlab", "IfcSpace")),
    ]:
        registry.quantities[resource.name] = resource

    for resource in [
        IfcNamedResource("IfcMaterial", "material"),
        IfcNamedResource("IfcMaterialLayerSet", "material", ("IfcWall", "IfcSlab")),
        IfcNamedResource("IfcMaterialConstituentSet", "material"),
    ]:
        registry.materials[resource.name] = resource

    for resource in [
        IfcNamedResource("Uniclass", "classification"),
        IfcNamedResource("OmniClass", "classification"),
        IfcNamedResource("bSDD", "classification"),
    ]:
        registry.classifications[resource.name] = resource

    for resource in [
        IfcNamedResource("spatial_containment", "relation", ("IfcRelContainedInSpatialStructure",)),
        IfcNamedResource("space_boundary", "relation", ("IfcRelSpaceBoundary",)),
    ]:
        registry.relations[resource.name] = resource

    for resource in [
        IfcNamedResource("internal", "boundary", ("IfcRelSpaceBoundary",)),
        IfcNamedResource("external", "boundary", ("IfcRelSpaceBoundary",)),
        IfcNamedResource("physical", "boundary", ("IfcRelSpaceBoundary",)),
    ]:
        registry.boundaries[resource.name] = resource

    return registry


DEFAULT_IFC_DATA_REGISTRY = create_default_ifc_data_registry()
