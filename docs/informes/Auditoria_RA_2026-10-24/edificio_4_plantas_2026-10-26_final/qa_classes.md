# QA: 2354 hallazgos clasificados

Carpeta `C:\Users\AntonioCViñas\AppData\Local\Temp\nosa_final2_s4`; plantas de 3000 mm; planta superior: storey 4.

| Clase | Hallazgos | Ejemplo |
|---|---|---|
| slab bars through a column cage, not set round its bars | 648 | 450x450mm 1513486 / 300mm RC Floor 1513556 01 / 04 - clash: centrelines 0 mm apart, bars 20 + 16 at (399838, 157, 2764) - keep the column bars where they are and either crank the beam bar inwards just before the j (id 1513817) |
| point 6: beam/column joint | 414 | 450x450mm 1513486 / 300x600mm 1513530 01 / 02 - clash: centrelines 0 mm apart, bars 20 + 20 at (400162, -0, 2460) - keep the column bars where they are and either crank the beam bar inwards just before the jo (id 1513820) |
| design: 300 beams with 3H20 leave no 75 mm poker gap (SMDSC MD B1) | 336 | 300x600mm 1513530  - 0 gap(s) of 75 mm in the top layer, 1 needed for a 300 mm beam (SMDSC 4th ed. MD B1) (id 1513530) |
| slab bars on each other (U-bars and main bars at edges and supports) | 256 | 300mm RC Floor 1513556 04 / 12 - clash: centrelines 4 mm apart, bars 16 + 16 at (399863, -136, 2748) (id 1514397) |
| slab bars on a beam's bars at the same level | 196 | 300x600mm 1513530 / 300mm RC Floor 1513556 01 / 04 - clash: centrelines 13 mm apart, bars 20 + 16 at (399831, 90, 2764) - keep the column bars where they are and either crank the beam bar inwards just before the j (id 1514155) |
| slab bars closer than s_min (U-bars and main bars at edges and supports) | 172 | 300mm RC Floor 1513556 06 / 09 - congested: clear gap 7 mm to a parallel bar (real size), 25 needed at (411063, 150, 2748) (id 1514400) |
| design: slab bars at 600 over the 400 allowed (SMDSC 6.2) | 88 | 300mm RC Floor 1513556 04 - pitch 600 mm over the 400 allowed (SMDSC 4th ed. 6.2) (id 1514397) |
| beam bars crossing at an interior joint (the secondary's 20 mm drop not enough) | 84 | 300x600mm 1513530 / 300x600mm 1513532 01 / 01 - clash: centrelines 5 mm apart, bars 20 + 20 at (399907, 90, 2896) - keep the column bars where they are and either crank the beam bar inwards just before the jo (id 1514155) |
| a column link 1 mm short of its cover at the joint | 27 | 450x450mm 1513486 02 - cover -1 mm under the bar size 10 (SMDSC 4th ed. 5.2.2) (id 1513824) |
| a column's lap crank on its top link | 27 | 450x450mm 1513486 01 / 02 - clash: centrelines 11 mm apart, bars 20 + 10 at (400166, 139, 2945) (id 1513817) |
| column/column at a storey joint: lap bars | 27 | 450x450mm 1513486 / 450x450mm 1513487 01 / 02 - clash: centrelines 11 mm apart, bars 20 + 10 at (400166, 138, 3055) - keep the column bars where they are and either crank the beam bar inwards just before the  (id 1513817) |
| info: bars a detailing rule added (confirm with design) | 21 | 1500x1500x500 1513485 03 - Links round the starter bars (SMDSC 4th ed. MD C1): detailing rule applied - confirm with design (id 1513485) |
| design: steel under the EC2 minimum | 20 | 300mm RC Floor 1513556 bottom_x - 0.129 % of b d under the minimum 0.157 % (EC2 9.3.1.1) (id 1513556) |
| point 7: column top L-bars | 16 | 450x450mm 1513489 01 / 01 - clash: centrelines 0 mm apart, bars 20 + 20 at (399838, 242, 11926) (id 1513844) |
| design: distribution bars over 450 (SMDSC MD S1) | 8 | 300mm RC Floor 1513556 04 - distribution bars H16 at 600 over the 450 of SMDSC 4th ed. MD S1 for a 300 mm slab (id 1514408) |
| a column's bars closer than s_min at a lap | 6 | 450x450mm 1513489 01 / 02 - congested: clear gap 10 mm to a parallel bar (real size), 25 needed at (399829, 155, 11936) (id 1513845) |
| other: Cover (stair) | 4 | Concrete Stair 1513671 06 - cover 15 mm under the aggregate size 20 (id 1514630) |
| other: Clash (stair) | 4 | Concrete Stair 1513671 06 / 11 - clash: centrelines 0 mm apart, bars 12 + 8 at (418931, -363, 1709) (id 1514630) |

## Por gravedad, comprobación, elemento y planta

| Clase | Gravedad | Comprobación | Elemento | Planta | Hallazgos |
|---|---|---|---|---|---|
| slab bars through a column cage, not set round its bars | Error | Joint clash | column / slab | storey 1 | 135 |
| slab bars through a column cage, not set round its bars | Error | Joint clash | column / slab | storey 2 | 135 |
| slab bars through a column cage, not set round its bars | Error | Joint clash | column / slab | storey 3 | 135 |
| slab bars through a column cage, not set round its bars | Error | Joint clash | column / slab | storey 4 | 117 |
| slab bars through a column cage, not set round its bars | Warning | Joint congestion | column / slab | storey 4 | 45 |
| slab bars through a column cage, not set round its bars | Warning | Joint congestion | column / slab | storey 1 | 27 |
| slab bars through a column cage, not set round its bars | Warning | Joint congestion | column / slab | storey 2 | 27 |
| slab bars through a column cage, not set round its bars | Warning | Joint congestion | column / slab | storey 3 | 27 |
| point 6: beam/column joint | Error | Joint clash | beam / column | storey 1 | 96 |
| point 6: beam/column joint | Error | Joint clash | beam / column | storey 2 | 96 |
| point 6: beam/column joint | Error | Joint clash | beam / column | storey 3 | 96 |
| point 6: beam/column joint | Error | Joint clash | beam / column | storey 4 | 54 |
| point 6: beam/column joint | Warning | Joint congestion | beam / column | storey 4 | 36 |
| point 6: beam/column joint | Warning | Joint congestion | beam / column | storey 1 | 12 |
| point 6: beam/column joint | Warning | Joint congestion | beam / column | storey 2 | 12 |
| point 6: beam/column joint | Warning | Joint congestion | beam / column | storey 3 | 12 |
| design: 300 beams with 3H20 leave no 75 mm poker gap (SMDSC MD B1) | Warning | Vibrator gap | beam | storey 1 | 84 |
| design: 300 beams with 3H20 leave no 75 mm poker gap (SMDSC MD B1) | Warning | Vibrator gap | beam | storey 2 | 84 |
| design: 300 beams with 3H20 leave no 75 mm poker gap (SMDSC MD B1) | Warning | Vibrator gap | beam | storey 3 | 84 |
| design: 300 beams with 3H20 leave no 75 mm poker gap (SMDSC MD B1) | Warning | Vibrator gap | beam | storey 4 | 84 |
| slab bars on each other (U-bars and main bars at edges and supports) | Error | Clash | slab | storey 1 | 64 |
| slab bars on each other (U-bars and main bars at edges and supports) | Error | Clash | slab | storey 2 | 64 |
| slab bars on each other (U-bars and main bars at edges and supports) | Error | Clash | slab | storey 3 | 64 |
| slab bars on each other (U-bars and main bars at edges and supports) | Error | Clash | slab | storey 4 | 64 |
| slab bars on a beam's bars at the same level | Error | Joint clash | beam / slab | storey 1 | 26 |
| slab bars on a beam's bars at the same level | Error | Joint clash | beam / slab | storey 2 | 26 |
| slab bars on a beam's bars at the same level | Error | Joint clash | beam / slab | storey 3 | 26 |
| slab bars on a beam's bars at the same level | Error | Joint clash | beam / slab | storey 4 | 26 |
| slab bars on a beam's bars at the same level | Warning | Joint congestion | beam / slab | storey 1 | 23 |
| slab bars on a beam's bars at the same level | Warning | Joint congestion | beam / slab | storey 2 | 23 |
| slab bars on a beam's bars at the same level | Warning | Joint congestion | beam / slab | storey 3 | 23 |
| slab bars on a beam's bars at the same level | Warning | Joint congestion | beam / slab | storey 4 | 23 |
| slab bars closer than s_min (U-bars and main bars at edges and supports) | Warning | Congestion | slab | storey 1 | 43 |
| slab bars closer than s_min (U-bars and main bars at edges and supports) | Warning | Congestion | slab | storey 2 | 43 |
| slab bars closer than s_min (U-bars and main bars at edges and supports) | Warning | Congestion | slab | storey 3 | 43 |
| slab bars closer than s_min (U-bars and main bars at edges and supports) | Warning | Congestion | slab | storey 4 | 43 |
| design: slab bars at 600 over the 400 allowed (SMDSC 6.2) | Warning | Pitch | slab | storey 1 | 22 |
| design: slab bars at 600 over the 400 allowed (SMDSC 6.2) | Warning | Pitch | slab | storey 2 | 22 |
| design: slab bars at 600 over the 400 allowed (SMDSC 6.2) | Warning | Pitch | slab | storey 3 | 22 |
| design: slab bars at 600 over the 400 allowed (SMDSC 6.2) | Warning | Pitch | slab | storey 4 | 22 |
| beam bars crossing at an interior joint (the secondary's 20 mm drop not enough) | Error | Joint clash | beam | storey 1 | 21 |
| beam bars crossing at an interior joint (the secondary's 20 mm drop not enough) | Error | Joint clash | beam | storey 2 | 21 |
| beam bars crossing at an interior joint (the secondary's 20 mm drop not enough) | Error | Joint clash | beam | storey 3 | 21 |
| beam bars crossing at an interior joint (the secondary's 20 mm drop not enough) | Error | Joint clash | beam | storey 4 | 21 |
| a column link 1 mm short of its cover at the joint | Error | Cover | column | storey 1 | 9 |
| a column link 1 mm short of its cover at the joint | Error | Cover | column | storey 2 | 9 |
| a column link 1 mm short of its cover at the joint | Error | Cover | column | storey 3 | 9 |
| a column's lap crank on its top link | Error | Clash | column | storey 1 | 9 |
| a column's lap crank on its top link | Error | Clash | column | storey 2 | 9 |
| a column's lap crank on its top link | Error | Clash | column | storey 3 | 9 |
| column/column at a storey joint: lap bars | Error | Joint clash | column | storey 2 | 9 |
| column/column at a storey joint: lap bars | Error | Joint clash | column | storey 3 | 9 |
| column/column at a storey joint: lap bars | Error | Joint clash | column | storey 4 | 9 |
| info: bars a detailing rule added (confirm with design) | Info | Rule-added bars | foundation | foundation | 9 |
| info: bars a detailing rule added (confirm with design) | Info | Rule-added bars | wall | storey 1 | 2 |
| info: bars a detailing rule added (confirm with design) | Info | Rule-added bars | wall | storey 2 | 2 |
| info: bars a detailing rule added (confirm with design) | Info | Rule-added bars | wall | storey 3 | 2 |
| info: bars a detailing rule added (confirm with design) | Info | Rule-added bars | wall | storey 4 | 2 |
| info: bars a detailing rule added (confirm with design) | Info | Rule-added bars | slab | storey 1 | 1 |
| info: bars a detailing rule added (confirm with design) | Info | Rule-added bars | slab | storey 2 | 1 |
| info: bars a detailing rule added (confirm with design) | Info | Rule-added bars | slab | storey 3 | 1 |
| info: bars a detailing rule added (confirm with design) | Info | Rule-added bars | slab | storey 4 | 1 |
| design: steel under the EC2 minimum | Warning | Steel ratio | slab | storey 1 | 4 |
| design: steel under the EC2 minimum | Warning | Steel ratio | slab | storey 2 | 4 |
| design: steel under the EC2 minimum | Warning | Steel ratio | slab | storey 3 | 4 |
| design: steel under the EC2 minimum | Warning | Steel ratio | slab | storey 4 | 4 |
| design: steel under the EC2 minimum | Warning | Steel ratio | wall | storey 1 | 1 |
| design: steel under the EC2 minimum | Warning | Steel ratio | wall | storey 2 | 1 |
| design: steel under the EC2 minimum | Warning | Steel ratio | wall | storey 3 | 1 |
| design: steel under the EC2 minimum | Warning | Steel ratio | wall | storey 4 | 1 |
| point 7: column top L-bars | Error | Clash | column | storey 4 | 16 |
| design: distribution bars over 450 (SMDSC MD S1) | Warning | Distribution pitch | slab | storey 1 | 2 |
| design: distribution bars over 450 (SMDSC MD S1) | Warning | Distribution pitch | slab | storey 2 | 2 |
| design: distribution bars over 450 (SMDSC MD S1) | Warning | Distribution pitch | slab | storey 3 | 2 |
| design: distribution bars over 450 (SMDSC MD S1) | Warning | Distribution pitch | slab | storey 4 | 2 |
| a column's bars closer than s_min at a lap | Warning | Congestion | column | storey 4 | 6 |
| other: Cover (stair) | Error | Cover | stair | storey 1 | 4 |
| other: Clash (stair) | Error | Clash | stair | storey 1 | 4 |
