# Evidence availability semantics

G1 records channel state independently of evidence value. `available` means a
connected source returned valid evidence (`a=1`); `no_matching_evidence` means a
connected source had none (`a=0`); `source_not_connected` means the source is
not on the formal path (`a=null`); `extraction_error` is a system fault and is
never encoded as zero; `not_applicable` is reserved for documented inapplicable
steps.  G1 has legacy memory disabled and no Dependency/Exemplar Store on the
formal path, so pK/pL/pE are `source_not_connected`, corresponding availability
values are null, and `use_availability_masks` remains `pending_g3`.
