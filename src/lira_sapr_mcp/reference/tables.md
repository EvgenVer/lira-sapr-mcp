# LIRA-SAPR input tables, FE types and text format

For LIRA-SAPR 2024 R2. "Verified" means the server's tests read or wrote it; "observed"
means seen in LIRA's example models, with column meanings not confirmed. When unsure,
read the table of a model that has such data (`lira_read_table`) before writing it.

## How tables work

- A row is a list of cells; the first cell is the node or element number (or object
  number: stiffness, load case). Empty cells are null.
- Values use LIRA's current input units: see `units` in `lira_model_summary`.
- `lira_write_table` without `numbers` replaces the whole table (new numbers add
  objects); with `numbers` it replaces only those rows. LIRA checks the rows and
  reports errors with 0-based row and column; on any error nothing changes.
- There is no table for loads: use `lira_read_loads` / `lira_set_loads`, or build a
  model in the text format (below).

## Tables

| Table | Columns | Status |
|---|---|---|
| `Nodes_Coordinates` | node, X, Y, Z | verified |
| `Elements_TypeAndNodes` | element, FE type, nodes as text `"1, 4"` | verified |
| `Nodes_Restraints` | node, X, Y, Z, UX, UY, UZ (1 = fixed, null = free), 1 more column (always null in examples) | verified (first 7) |
| `Elements_Stiffnesses` | element, stiffness number | verified |
| `Elements_DesignSectionsCount` | element, number of design sections (bars: default 2, start and end) | verified |
| `Stiffnesses` | number, section type code, colour `#rrggbb`, null, parameters as text, then nulls | observed; create stiffnesses with the text format |
| `Stiffnesses_Factors` | element, a factor (1.0); it does not change a linear analysis (verified) — to change stiffness, assign another stiffness | observed |
| `LoadCases` | number, name, problem text (`"1. Основная задача: ..."`), kind (`Постоянное(П)`, `Длительное(Д)`, `Кратковременное(К)`, `Мгновенное(М)`, `Особое ...`), null | verified (number, name, kind) |
| `DCL` | first row all null; then per load case: number, name, kind, null, sign `+`, then 4 coefficients (e.g. `0, 1.1, 1, 0`) | observed |
| `StructuralBlocks` | elements as text `"1-1080 1889-1924"`, `Блок`, block number, null, null, name, colour | observed |
| `Bars_LocalAxes`, `Plates_LocalAxes`, `Plates_AxesOfOrthotropy` | element, angle | observed |
| `Plates_Offsets` | element, offset | observed |
| `Bars_Offsets` | element, 6 offset values, `-` | observed |
| `Bars_C1C2` | element + 12 cells, the last one the model of the base (`0 - Линейная`) | observed |
| `Plates_C1C2` | element, C1, C2 and 3 more cells, the last one `0 - Линейная` | observed |
| `Bars_Hinges` | element + 14 cells (null = no hinge) | observed |
| `Nodes_LocalAxes` | node + 4 cells | observed |
| `Elements_Materials` | element + 2 cells | observed |
| `CollectionOfMasses` | a matrix 1001 cells wide: a header row, then a row per load case (`"1.Загружение 1"`) | observed |

Empty in all examples, columns unknown: `AssemblageStages`, `Bars_InternalForces`,
`ConstructionAxes`, `CoupledDOFs`, `ElevationMarks`, `NonlinearDiagrams`, `PRBs`,
`Solids_LocalAxes`, `Solids_AxesOfOrthotropy`, `Special_C1C2`.

Section type codes seen in `Stiffnesses`: 0 rectangle (`B`, `H`), 1 T-section (`B`, `H`,
`B1`, `H1`), 36 plate (`H` thickness, `E`, `V` Poisson's ratio, `Ro` density),
1001 steel profile from a catalogue (`File`, `Shape`).

## Finite element types

| FE type | Meaning | Nodes | Seen in |
|---|---|---|---|
| 10 | universal space bar | 2 | frames (example 01, 04) |
| 11 | rectangular plate (bending) | 4 | slab (example 02, model type 3) |
| 41 | universal rectangular shell | 4 | wall-beam (example 04) |
| 44 | universal quadrilateral shell | 4 | slab on elastic base (example 04) |

Other types exist (triangular plates and shells, plane stress, solids, special
elements); see LIRA's FE library. `elements_by_fe_type` in `lira_model_summary` shows
which types a model uses.

Model types (`model_type`, degrees of freedom per node): 1 2D truss in XOZ (X, Z),
2 2D frame in XOZ (X, Z, UY), 3 grillage or plate in XOY (Z, UX, UY), 4 3D truss
(X, Y, Z), 5 general 3D (X, Y, Z, UX, UY, UZ).

## Text format

`lira_import_text_model` takes it; `lira_export_text` shows any model in it. Documents
`( N/ entry/ entry/ ... )`, each starting a line. A verified 6 x 3 m portal frame:

```text
( 0/ 1; FRAME/ 2; 5/ 33; M 1 CM 100 T 1 C 1/ )
( 1/ 10 1 1 3/ 10 1 2 4/ 10 1 3 4/ )
( 3/ 1 S0 3E6 40 60/ 0 RO 2.5/ )
( 4/ 0 0 0/ 6 0 0/ 0 0 3/ 6 0 3/ )
( 5/ 1 1 2 3 4 5 6/ 2 1 2 3 4 5 6/ )
( 6/ 3 6 3 1 1/ )
( 7/ 1 10/ )
```

- 0: `1; name/` the model name, `2; type/` the model type, `33; .../` the units of the
  text; keep `33; M 1 CM 100 T 1 C 1/` (m, section sizes in cm, t, degrees C) so that
  the values below read as described.
- 1: elements in order, `FE-type stiffness node node .../`.
- 3: stiffnesses, `number S0 E B H/` a rectangular section (E in t/m2, B and H in cm);
  `0 RO weight/` the weight per length (t/m) for the stiffness above: `RO 2.5` with a
  40 x 60 cm section becomes density `Ro:10.4167` (t/m3) in the `Stiffnesses` table.
  Self weight (`lira_self_weight`) uses it; it is a load of type 16 in document 6.
- 4: node coordinates in order, `X Y Z/`.
- 5: restraints, `node direction direction .../` with directions 1-6 = X Y Z UX UY UZ.
- 6: loads, `target type direction row case/`: type 0 is a nodal load (target is a
  node), type 6 a uniform load on a bar; direction 3 = global Z, a positive value acts
  downward; `row` points to document 7.
- 7: load values, `row value value .../`.
