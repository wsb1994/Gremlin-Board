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
# paint Metal4 across the SRAM (its Metal4 is an obstruction). The
# stdcell_grid straps are Metal4 *pins* and must span the die, so the
# eight strap positions the macro would cut are left out of that grid
# above. Supply for the SRAM and for the standard cells in its column
# comes from three pieces, all on layers the precheck allows:
#
#  1. sramcol: non-pin Metal4 straps at the macro's own VDD!/VSS! pin
#     columns. pdngen clips them at the macro, leaving a full-height
#     segment below it (rails via up to it) and a short one above.
#  2. sramtie: Metal3 bars in the halo bands just below (VGND, VPWR)
#     and just above (VPWR) the macro. They cross every Metal4 strap,
#     inside and outside the column, and pdngen vias them together.
#  3. loom_tie_sram_pins (after pdngen): for every macro supply pin
#     that reaches the macro edge, a Metal4 bridge of the pin's own
#     width overlapping the pin, the clipped sramcol strap and the
#     Metal3 bar, with a row of Via3 cuts onto the bar. Geometry is
#     read from the placed instance, not typed in.
#
# Verify: OpenROAD check_power_grid (run by the flow) and
# scripts/check_pg_klayout.py on the final GDS.

set ::loom_sram_inst engine.imem.imem_sram
# Macro-relative x centres of the SRAM supply pins that get a strap.
# Outer pin groups only: every other VDD!/VSS! pair, 17.68 um apart.
set ::loom_col_vpwr {8.355 43.715 79.075 114.435 287.835 323.195 358.555 393.915}
set ::loom_col_vgnd {17.195 52.555 87.915 123.275 296.675 332.035 367.395 402.755}

proc loom_core_origin {} {
    set block [ord::get_db_block]
    set dbu [[$block getTech] getDbUnitsPerMicron]
    set core [$block getCoreArea]
    return [list [expr {[$core xMin] / double($dbu)}] [expr {[$core yMin] / double($dbu)}]]
}

proc loom_sram_x {} {
    set block [ord::get_db_block]
    set dbu [[$block getTech] getDbUnitsPerMicron]
    set inst [$block findInst $::loom_sram_inst]
    if {$inst eq "NULL"} { error "SRAM instance $::loom_sram_inst not placed" }
    return [expr {[[$inst getBBox] xMin] / double($dbu)}]
}

define_pdn_grid \
    -name sramcol \
    -starts_with POWER \
    -voltage_domains CORE

lassign [loom_core_origin] core_x core_y
set sram_x [loom_sram_x]
foreach {net centres} [list $::env(VDD_NET) $::loom_col_vpwr $::env(GND_NET) $::loom_col_vgnd] {
    foreach c $centres {
        add_pdn_stripe \
            -grid sramcol \
            -layer Metal4 \
            -width $::env(PDN_VWIDTH) \
            -pitch 2000 \
            -offset [format %.3f [expr {$sram_x + $c - $core_x}]] \
            -number_of_straps 1 \
            -nets $net
    }
}
add_pdn_connect -grid sramcol -layers "Metal1 Metal4"
add_pdn_connect -grid sramcol -layers "Metal3 Metal4"

# Metal3 bars: 3.5 um below the macro (VGND), 7 um below (VPWR), 5 um
# above (VPWR). Absolute y = core_y + offset.
set sram_y0 [expr {559.440}]
set sram_y1 [expr {559.440 + 136.970}]
set block [ord::get_db_block]
set inst [$block findInst $::loom_sram_inst]
set dbu [[$block getTech] getDbUnitsPerMicron]
set sram_y0 [expr {[[$inst getBBox] yMin] / double($dbu)}]
set sram_y1 [expr {[[$inst getBBox] yMax] / double($dbu)}]
set ::loom_bar_vgnd_lo [expr {$sram_y0 - 8.44}]
set ::loom_bar_vpwr_lo [expr {$sram_y0 - 4.94}]
set ::loom_bar_vpwr_hi [expr {$sram_y1 + 5.09}]

define_pdn_grid \
    -name sramtie \
    -starts_with POWER \
    -voltage_domains CORE
foreach {net y} [list $::env(GND_NET) $::loom_bar_vgnd_lo $::env(VDD_NET) $::loom_bar_vpwr_lo $::env(VDD_NET) $::loom_bar_vpwr_hi] {
    add_pdn_stripe \
        -grid sramtie \
        -layer Metal3 \
        -width 0.48 \
        -pitch 2000 \
        -offset [format %.3f [expr {$y - $core_y}]] \
        -number_of_straps 1 \
        -nets $net
}
add_pdn_connect -grid sramtie -layers "Metal3 Metal4"

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
    set inst [$block findInst $::loom_sram_inst]
    if {[$inst getOrient] ne "R0"} { error "loom_tie_sram_pins: only orientation N is handled" }
    lassign [$inst getOrigin] ox oy
    set bb [$inst getBBox]
    set y0 [$bb yMin]
    set y1 [$bb yMax]
    set netmap [dict create VDD! $::env(VDD_NET) VDDARRAY! $::env(VDD_NET) VSS! $::env(GND_NET)]
    set bars [dict create \
        bottom,$::env(GND_NET) $::loom_bar_vgnd_lo \
        bottom,$::env(VDD_NET) $::loom_bar_vpwr_lo \
        top,$::env(VDD_NET) $::loom_bar_vpwr_hi]
    set reach_out [expr {int(round(10.0 * $dbu))}]   ;# beyond the macro edge (halo band)
    set reach_in  [expr {int(round(8.0 * $dbu))}]    ;# overlap into the pin
    set inset     [expr {int(round(0.1 * $dbu))}]    ;# bridge sits strictly inside the pin outline (Magic subcell-overlap rule)
    set cut_pitch [expr {int(round(0.7 * $dbu))}]    ;# Magic V3.b wants >= 0.42 um between cuts
    # Where a sramcol strap crosses the bar, pdngen already placed a via
    # array; extra single cuts there abut it (Magic). Keep clear of them.
    set keep_out [expr {int(round(($::env(PDN_VWIDTH) / 2.0 + 0.45) * $dbu))}]
    set strap_xs [list]
    foreach c [concat $::loom_col_vpwr $::loom_col_vgnd] {
        lappend strap_xs [expr {$ox + int(round($c * $dbu))}]
    }
    set n 0
    foreach mterm [[$inst getMaster] getMTerms] {
        set pname [$mterm getName]
        if {![dict exists $netmap $pname]} { continue }
        set netname [dict get $netmap $pname]
        set net [$block findNet $netname]
        foreach mpin [$mterm getMPins] {
            foreach geom [$mpin getGeometry] {
                if {[[$geom getTechLayer] getName] ne "Metal4"} { continue }
                set rx0 [expr {[$geom xMin] + $ox + $inset}]; set rx1 [expr {[$geom xMax] + $ox - $inset}]
                set ry0 [expr {[$geom yMin] + $oy}]; set ry1 [expr {[$geom yMax] + $oy}]
                foreach side {bottom top} {
                    if {$side eq "bottom" && $ry0 != $y0} { continue }
                    if {$side eq "top" && $ry1 != $y1} { continue }
                    if {![dict exists $bars $side,$netname]} { continue }
                    set bar_y [expr {int(round([dict get $bars $side,$netname] * $dbu))}]
                    if {$side eq "bottom"} {
                        set by0 [expr {$y0 - $reach_out}]; set by1 [expr {$y0 + $reach_in}]
                    } else {
                        set by0 [expr {$y1 - $reach_in}]; set by1 [expr {$y1 + $reach_out}]
                    }
                    set sw [odb::dbSWire_create $net ROUTED]
                    odb::dbSBox_create $sw $m4 $rx0 $by0 $rx1 $by1 STRIPE
                    # row of single cuts across the pin width, 0.6 um pitch, 0.5 um in from each side
                    set cx0 [expr {$rx0 + int(round(0.5 * $dbu))}]
                    set cx1 [expr {$rx1 - int(round(0.5 * $dbu))}]
                    for {set cx $cx0} {$cx <= $cx1} {incr cx $cut_pitch} {
                        set clear 1
                        foreach sx $strap_xs {
                            if {abs($cx - $sx) < $keep_out} { set clear 0; break }
                        }
                        if {$clear} { odb::dbSBox_create $sw $via $cx $bar_y STRIPE }
                    }
                    incr n
                }
            }
        }
    }
    puts "LOOM: tied $n SRAM supply pin edges (Metal4 bridges + Via3 rows)"
}
