# server.tcl — VMD-side control server for VMD-Hydrate-MCP.
#
# Security (PLAN §13 S1/S2/S3):
#   * Bound to 127.0.0.1 on an ephemeral port; the port is printed to stdout as
#     "SERVER_LISTENING <port>" for the parent to read.
#   * Every request must present the per-session token (read from the 0600 file
#     named by env VMDHYDRATE_TOKENFILE); mismatches are rejected.
#   * Requests are dispatched by an ALLOWLIST of named recipe procs. The payload
#     is parsed as a Tcl list, so each argument (e.g. a selection string) is an
#     inert literal element and can never break out into command substitution.
#     There is NO eval of arbitrary client Tcl on this path.
#   * Framing is length-prefixed: "<nbytes>\n" then exactly nbytes, payload =
#     "<token>\n<tcl-list request>". Replies are framed the same way.
#
# This file is server-authored and trusted; only the parent Python process holds
# the token, and it only ever sends vetted recipe requests.

set ::TOKEN ""
if {[info exists ::env(VMDHYDRATE_TOKENFILE)]} {
    set tf $::env(VMDHYDRATE_TOKENFILE)
    if {[catch {open $tf r} fh] == 0} {
        set ::TOKEN [string trim [read $fh]]
        close $fh
    }
}

# ---- recipe library (the ONLY callable commands) --------------------------- #
proc recipe_ping {} { return "pong [vmdinfo version] [vmdinfo arch]" }

proc recipe_version {} { return [vmdinfo version] }

proc recipe_load {path {ftype auto}} {
    if {$ftype eq "auto"} {
        set m [mol new $path waitfor all]
    } else {
        set m [mol new $path type $ftype waitfor all]
    }
    return "molid $m numatoms [molinfo $m get numatoms] numframes [molinfo $m get numframes]"
}

proc recipe_addfile {molid path} {
    mol addfile $path waitfor all molid $molid
    return "molid $molid numframes [molinfo $molid get numframes]"
}

proc recipe_listmols {} {
    set out {}
    foreach m [molinfo list] {
        lappend out "molid $m numatoms [molinfo $m get numatoms] numframes [molinfo $m get numframes]"
    }
    return [join $out " | "]
}

proc recipe_delete {molid} { mol delete $molid; return "deleted $molid" }

# Replace representations on a molecule. style/color/material are VMD keywords;
# seltext is an atom-selection string bound as a single literal list element.
proc recipe_representation {molid style color material seltext} {
    set nrep [molinfo $molid get numreps]
    for {set i [expr {$nrep-1}]} {$i >= 0} {incr i -1} { mol delrep $i $molid }
    mol representation $style
    mol color $color
    mol material $material
    mol selection $seltext
    mol addrep $molid
    set sel [atomselect $molid $seltext]
    set nsel [$sel num]
    $sel delete
    return "reps [molinfo $molid get numreps] sel $nsel"
}

# Export the current scene to a Tachyon scene file (no display needed). The
# parent rasterizes it with the standalone tachyon binary (resolution control)
# and converts to PNG. We never call `display resize/update` (crashes headless).
proc recipe_render_scene {molid outpath} {
    render Tachyon $outpath
    return "scene $outpath exists [file exists $outpath]"
}

proc recipe_set_frame {molid frame} {
    animate goto $frame
    return "frame [molinfo $molid get frame]"
}

proc recipe_clearreps {molid} {
    set nrep [molinfo $molid get numreps]
    for {set i [expr {$nrep-1}]} {$i >= 0} {incr i -1} { mol delrep $i $molid }
    return "reps [molinfo $molid get numreps]"
}

# Add a representation colored by a solid ColorID (0=blue,1=red,4=yellow,7=green,
# 2=gray, ...). Used to paint cages by type without deleting existing reps.
proc recipe_addrep_colorid {molid style colorid material seltext} {
    mol representation {*}$style
    mol color ColorID $colorid
    mol material $material
    mol selection $seltext
    mol addrep $molid
    set sel [atomselect $molid $seltext]
    set nsel [$sel num]
    $sel delete
    return "reps [molinfo $molid get numreps] sel $nsel"
}

# Rotate the camera by degrees about an axis (headless-safe; unlike display resize).
proc recipe_rotate {axis degrees} {
    rotate $axis by $degrees
    return "rotated $axis $degrees"
}

# Fit the view to the loaded molecules (headless-safe, unlike display resize/update).
proc recipe_resetview {molid} {
    display resetview
    return "resetview"
}

# Zoom by a multiplicative factor.
proc recipe_scale {factor} {
    scale by $factor
    return "scaled $factor"
}

# Configure a photorealistic scene: projection + ambient occlusion + shadows +
# antialiasing + background. Honored by the Tachyon renderer (no OSPRay on this
# build). projection is "Orthographic" or "Perspective".
proc recipe_scene {projection bgr bgg bgb aoambient aodirect} {
    display projection $projection
    display shadows on
    display ambientocclusion on
    display aoambient $aoambient
    display aodirect $aodirect
    display antialias on
    display depthcue off
    color Display Background black
    color change rgb black $bgr $bgg $bgb
    return "scene projection=$projection bg=$bgr,$bgg,$bgb ao=$aoambient/$aodirect"
}

# VMD color-id -> color-name table (0..32). `color change rgb` needs the NAME,
# while `mol color ColorID` uses the numeric id, so we bridge the two here.
set ::COLORNAMES {blue red gray orange yellow tan silver green white pink cyan \
    purple lime mauve ochre iceblue black yellow2 yellow3 green2 green3 cyan2 \
    cyan3 blue2 blue3 violet violet2 magenta magenta2 red2 red3 orange2 orange3}

# Redefine the RGB (0..1 floats) of a stock color id so we can match an exact
# per-cage-type palette. Use ids >= 17 to avoid recoloring the x/y/z axis colors.
proc recipe_setcolor {colorid r g b} {
    set name [lindex $::COLORNAMES $colorid]
    if {$name eq ""} { error "colorid $colorid out of range (0-32)" }
    color change rgb $name $r $g $b
    return "colorid $colorid ($name) = $r $g $b"
}

set ::RECIPES {
    recipe_ping recipe_version recipe_load recipe_addfile recipe_listmols
    recipe_delete recipe_representation recipe_render_scene recipe_set_frame
    recipe_clearreps recipe_addrep_colorid recipe_rotate recipe_resetview recipe_scale
    recipe_scene recipe_setcolor
}

proc ::dispatch {req} {
    set name [lindex $req 0]
    if {[lsearch -exact $::RECIPES $name] < 0} {
        error "unknown recipe: $name"
    }
    return [{*}$req]
}

proc ::reply {chan code res} {
    set body "$code\n$res"
    puts $chan [string length $body]
    puts -nonewline $chan $body
    flush $chan
}

proc ::serve {chan addr port} {
    fconfigure $chan -translation binary -encoding binary -blocking 1
    while {1} {
        set hdr [gets $chan]
        if {[eof $chan]} break
        if {![string is integer -strict $hdr]} continue
        set payload [read $chan $hdr]
        set nl [string first "\n" $payload]
        if {$nl < 0} { ::reply $chan 1 "bad frame"; continue }
        set tok [string range $payload 0 [expr {$nl - 1}]]
        set req [string range $payload [expr {$nl + 1}] end]
        if {$::TOKEN eq "" || $tok ne $::TOKEN} { ::reply $chan 1 "auth failed"; continue }
        set code [catch {::dispatch $req} res]
        ::reply $chan $code $res
    }
    catch {close $chan}
}

if {[catch {socket -server ::serve -myaddr 127.0.0.1 0} ::srv]} {
    puts "SERVER_FAIL $::srv"
    quit
}
set ::PORT [lindex [fconfigure $::srv -sockname] 2]
puts "SERVER_LISTENING $::PORT"
flush stdout
vwait ::forever
