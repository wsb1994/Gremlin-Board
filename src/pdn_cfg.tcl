# Copyright 2025 LibreLane Contributors
#
# Adapted from OpenLane
#
# Copyright 2020-2022 Efabless Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

source $::env(SCRIPTS_DIR)/openroad/common/io.tcl
source $::env(SCRIPTS_DIR)/openroad/common/set_global_connections.tcl
set_global_connections

set secondary []
foreach vdd $::env(VDD_NETS) gnd $::env(GND_NETS) {
    if { $vdd != $::env(VDD_NET)} {
        lappend secondary $vdd

        set db_net [[ord::get_db_block] findNet $vdd]
        if {$db_net == "NULL"} {
            set net [odb::dbNet_create [ord::get_db_block] $vdd]
            $net setSpecial
            $net setSigType "POWER"
        }
    }

    if { $gnd != $::env(GND_NET)} {
        lappend secondary $gnd

        set db_net [[ord::get_db_block] findNet $gnd]
        if {$db_net == "NULL"} {
            set net [odb::dbNet_create [ord::get_db_block] $gnd]
            $net setSpecial
            $net setSigType "GROUND"
        }
    }
}

set_voltage_domain -name CORE -power $::env(VDD_NET) -ground $::env(GND_NET) \
    -secondary_power $secondary



if { $::env(PDN_MULTILAYER) == 1 } {

    set arg_list [list]
    if { $::env(PDN_ENABLE_PINS) } {
        lappend arg_list -pins "$::env(PDN_VERTICAL_LAYER) $::env(PDN_HORIZONTAL_LAYER)"
    }

    define_pdn_grid \
        -name stdcell_grid \
        -starts_with POWER \
        -voltage_domain CORE \
        {*}$arg_list

    set arg_list [list]
    append_if_equals arg_list PDN_EXTEND_TO "core_ring" -extend_to_core_ring
    append_if_equals arg_list PDN_EXTEND_TO "boundary" -extend_to_boundary

    add_pdn_stripe \
        -grid stdcell_grid \
        -layer $::env(PDN_VERTICAL_LAYER) \
        -width $::env(PDN_VWIDTH) \
        -pitch $::env(PDN_VPITCH) \
        -offset $::env(PDN_VOFFSET) \
        -spacing $::env(PDN_VSPACING) \
        -starts_with POWER \
        {*}$arg_list

    add_pdn_stripe \
        -grid stdcell_grid \
        -layer $::env(PDN_HORIZONTAL_LAYER) \
        -width $::env(PDN_HWIDTH) \
        -pitch $::env(PDN_HPITCH) \
        -offset $::env(PDN_HOFFSET) \
        -spacing $::env(PDN_HSPACING) \
        -starts_with POWER \
        {*}$arg_list

    add_pdn_connect \
        -grid stdcell_grid \
        -layers "$::env(PDN_VERTICAL_LAYER) $::env(PDN_HORIZONTAL_LAYER)"
} else {

    set arg_list [list]
    if { $::env(PDN_ENABLE_PINS) } {
        lappend arg_list -pins "$::env(PDN_VERTICAL_LAYER)"
    }

    define_pdn_grid \
        -name stdcell_grid \
        -starts_with POWER \
        -voltage_domain CORE \
        {*}$arg_list

    set arg_list [list]
    append_if_equals arg_list PDN_EXTEND_TO "core_ring" -extend_to_core_ring
    append_if_equals arg_list PDN_EXTEND_TO "boundary" -extend_to_boundary

    # Vertical Metal4 is the power-pin layer. Every pin rectangle must
    # reach within 10um of both die edges, so straps that the SRAM Metal4
    # obstruction would cut are not drawn on this grid. Pitch/offset match
    # the template grid (center = core_llx + offset, core_llx = 2.880):
    # VPWR at offset 10+50*n, VGND at 14.1+50*n, skipping n=9..16.
    foreach off {10.000 60.000 110.000 160.000 210.000 260.000 310.000 360.000 410.000 860.000 910.000 960.000 1010.000 1060.000 1110.000 1160.000 1210.000 1260.000} {
        add_pdn_stripe \
            -grid stdcell_grid \
            -layer $::env(PDN_VERTICAL_LAYER) \
            -width $::env(PDN_VWIDTH) \
            -pitch 2000 \
            -offset $off \
            -number_of_straps 1 \
            -nets $::env(VDD_NET)
    }
    foreach off {14.100 64.100 114.100 164.100 214.100 264.100 314.100 364.100 414.100 864.100 914.100 964.100 1014.100 1064.100 1114.100 1164.100 1214.100 1264.100} {
        add_pdn_stripe \
            -grid stdcell_grid \
            -layer $::env(PDN_VERTICAL_LAYER) \
            -width $::env(PDN_VWIDTH) \
            -pitch 2000 \
            -offset $off \
            -number_of_straps 1 \
            -nets $::env(GND_NET)
    }
}

# Adds the standard cell rails if enabled.
if { $::env(PDN_ENABLE_RAILS) == 1 } {
    add_pdn_stripe \
        -grid stdcell_grid \
        -layer $::env(PDN_RAIL_LAYER) \
        -width $::env(PDN_RAIL_WIDTH) \
        -followpins

    add_pdn_connect \
        -grid stdcell_grid \
        -layers "$::env(PDN_RAIL_LAYER) $::env(PDN_VERTICAL_LAYER)"
}


# Adds the core ring if enabled.
if { $::env(PDN_CORE_RING) == 1 } {
    if { $::env(PDN_MULTILAYER) == 1 } {
        set arg_list [list]
        append_if_flag arg_list PDN_CORE_RING_ALLOW_OUT_OF_DIE -allow_out_of_die
        append_if_flag arg_list PDN_CORE_RING_CONNECT_TO_PADS -connect_to_pads
        append_if_equals arg_list PDN_EXTEND_TO "boundary" -extend_to_boundary
        append_if_exists_argument arg_list PDN_CORE_RING_CONNECT_TO_PAD_LAYERS -connect_to_pad_layers

        set pdn_core_vertical_layer $::env(PDN_VERTICAL_LAYER)
        set pdn_core_horizontal_layer $::env(PDN_HORIZONTAL_LAYER)

        if { [info exists ::env(PDN_CORE_VERTICAL_LAYER)] } {
            set pdn_core_vertical_layer $::env(PDN_CORE_VERTICAL_LAYER)
        }

        if { [info exists ::env(PDN_CORE_HORIZONTAL_LAYER)] } {
            set pdn_core_horizontal_layer $::env(PDN_CORE_HORIZONTAL_LAYER)
        }

        add_pdn_ring \
            -grid stdcell_grid \
            -layers "$pdn_core_vertical_layer $pdn_core_horizontal_layer" \
            -widths "$::env(PDN_CORE_RING_VWIDTH) $::env(PDN_CORE_RING_HWIDTH)" \
            -spacings "$::env(PDN_CORE_RING_VSPACING) $::env(PDN_CORE_RING_HSPACING)" \
            -core_offset "$::env(PDN_CORE_RING_VOFFSET) $::env(PDN_CORE_RING_HOFFSET)" \
            {*}$arg_list

        if { [info exists ::env(PDN_CORE_VERTICAL_LAYER)] } {
            add_pdn_connect \
                -grid stdcell_grid \
                -layers "$::env(PDN_CORE_VERTICAL_LAYER) $::env(PDN_HORIZONTAL_LAYER)"
        }

        if { [info exists ::env(PDN_CORE_HORIZONTAL_LAYER)] } {
            add_pdn_connect \
                -grid stdcell_grid \
                -layers "$::env(PDN_CORE_HORIZONTAL_LAYER) $::env(PDN_VERTICAL_LAYER)"
        }

        if { [info exists ::env(PDN_CORE_VERTICAL_LAYER)] && [info exists ::env(PDN_CORE_HORIZONTAL_LAYER)] } {
            add_pdn_connect \
                -grid stdcell_grid \
                -layers "$::env(PDN_CORE_VERTICAL_LAYER) $::env(PDN_CORE_HORIZONTAL_LAYER)"
        }

    } else {
        throw APPLICATION "PDN_CORE_RING cannot be used when PDN_MULTILAYER is set to false."
    }
}

# CMOS5L precheck forbids TopMetal1 and TopVia1, and pdngen will not
# paint Metal4 across the SRAM (the pins themselves are obstructions).
# These Metal3 bars sit in the placement halo and via down onto the core
# Metal4 straps. After pdngen, loom_tie_sram_pins overlaps each SRAM
# power pin with a Metal4 bridge and a Via3 onto the matching bar.
# Offsets are from the core origin (x 2.880, y 3.780).
define_pdn_grid \
    -name sramtie \
    -starts_with POWER \
    -voltage_domains CORE

add_pdn_stripe \
    -grid sramtie \
    -layer Metal3 \
    -width 0.48 \
    -pitch 2000 \
    -offset 547.220 \
    -number_of_straps 1 \
    -nets $::env(GND_NET)
add_pdn_stripe \
    -grid sramtie \
    -layer Metal3 \
    -width 0.48 \
    -pitch 2000 \
    -offset 550.720 \
    -number_of_straps 1 \
    -nets $::env(VDD_NET)
add_pdn_stripe \
    -grid sramtie \
    -layer Metal3 \
    -width 0.48 \
    -pitch 2000 \
    -offset 697.720 \
    -number_of_straps 1 \
    -nets $::env(VDD_NET)
add_pdn_connect \
    -grid sramtie \
    -layers "Metal3 Metal4"

rename pdngen _loom_pdngen_orig
proc pdngen {args} {
    _loom_pdngen_orig {*}$args
    loom_tie_sram_pins
}


proc loom_tie_sram_pins {} {
  set block [ord::get_db_block]
  set tech [$block getTech]
  set dbu [$tech getDbUnitsPerMicron]
  set m4 [$tech findLayer Metal4]
  set via [$tech findVia Via3_XX]
  if {$via eq "NULL"} { error "Via3_XX not found" }
  foreach {netname cx y0 y1 vy} {
    VGND 837.155 550.500 696.410 551.000
    VGND 819.475 550.500 696.410 551.000
    VGND 801.795 550.500 696.410 551.000
    VGND 784.115 550.500 696.410 551.000
    VGND 766.435 550.500 696.410 551.000
    VGND 748.755 550.500 696.410 551.000
    VGND 731.075 550.500 696.410 551.000
    VGND 713.395 550.500 696.410 551.000
    VGND 683.000 550.500 696.410 551.000
    VGND 672.700 550.500 696.410 551.000
    VGND 657.250 550.500 696.410 551.000
    VGND 646.950 550.500 696.410 551.000
    VGND 641.800 550.500 696.410 551.000
    VGND 631.500 550.500 696.410 551.000
    VGND 616.050 550.500 696.410 551.000
    VGND 605.750 550.500 696.410 551.000
    VGND 575.355 550.500 696.410 551.000
    VGND 557.675 550.500 696.410 551.000
    VGND 539.995 550.500 696.410 551.000
    VGND 522.315 550.500 696.410 551.000
    VGND 504.635 550.500 696.410 551.000
    VGND 486.955 550.500 696.410 551.000
    VGND 469.275 550.500 696.410 551.000
    VGND 451.595 550.500 696.410 551.000
    VPWR 845.995 554.200 606.335 554.500
    VPWR 828.315 554.200 606.335 554.500
    VPWR 810.635 554.200 606.335 554.500
    VPWR 792.955 554.200 606.335 554.500
    VPWR 775.275 554.200 606.335 554.500
    VPWR 757.595 554.200 606.335 554.500
    VPWR 739.915 554.200 606.335 554.500
    VPWR 722.235 554.200 606.335 554.500
    VPWR 677.850 554.200 696.410 554.500
    VPWR 667.550 554.200 696.410 554.500
    VPWR 662.400 554.200 696.410 554.500
    VPWR 652.100 554.200 696.410 554.500
    VPWR 636.650 554.200 696.410 554.500
    VPWR 626.350 554.200 696.410 554.500
    VPWR 621.200 554.200 696.410 554.500
    VPWR 610.900 554.200 696.410 554.500
    VPWR 566.515 554.200 606.335 554.500
    VPWR 548.835 554.200 606.335 554.500
    VPWR 531.155 554.200 606.335 554.500
    VPWR 513.475 554.200 606.335 554.500
    VPWR 495.795 554.200 606.335 554.500
    VPWR 478.115 554.200 606.335 554.500
    VPWR 460.435 554.200 606.335 554.500
    VPWR 442.755 554.200 606.335 554.500
    VPWR 845.995 613.050 701.800 701.500
    VPWR 828.315 613.050 701.800 701.500
    VPWR 810.635 613.050 701.800 701.500
    VPWR 792.955 613.050 701.800 701.500
    VPWR 775.275 613.050 701.800 701.500
    VPWR 757.595 613.050 701.800 701.500
    VPWR 739.915 613.050 701.800 701.500
    VPWR 722.235 613.050 701.800 701.500
    VPWR 566.515 613.050 701.800 701.500
    VPWR 548.835 613.050 701.800 701.500
    VPWR 531.155 613.050 701.800 701.500
    VPWR 513.475 613.050 701.800 701.500
    VPWR 495.795 613.050 701.800 701.500
    VPWR 478.115 613.050 701.800 701.500
    VPWR 460.435 613.050 701.800 701.500
    VPWR 442.755 613.050 701.800 701.500
  } {
    set net [$block findNet $netname]
    set sw [odb::dbSWire_create $net ROUTED]
    set x0 [expr {int(round(($cx - 0.18) * $dbu))}]
    set x1 [expr {int(round(($cx + 0.18) * $dbu))}]
    set iy0 [expr {int(round($y0 * $dbu))}]
    set iy1 [expr {int(round($y1 * $dbu))}]
    odb::dbSBox_create $sw $m4 $x0 $iy0 $x1 $iy1 STRIPE
    set vx [expr {int(round($cx * $dbu))}]
    set vyi [expr {int(round($vy * $dbu))}]
    odb::dbSBox_create $sw $via $vx $vyi STRIPE
  }
  puts "LOOM: tied SRAM power pins"
}
