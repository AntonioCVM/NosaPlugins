# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — single source of truth for the generator version
string. Deferred from Phase F0 (see F0's own delivery note) to F1,
where it's actually needed: threaded through ctx['generator_version']
into NOSA_Rebar_Generator_Version, stamped on every Rebar this plugin
creates (nosa_utils.shared_params.stamp_provenance, called from
rebar_batch.py).

script.py reads this for its own __version__ rather than the other
way around, so there is exactly one place this number lives.
"""
RA_VERSION = "1.0.0-dev"
