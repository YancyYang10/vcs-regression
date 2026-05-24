set wave $env(wave)
set tc $env(tc)
set seed $env(seed)
set RESULT_DIR $env(RESULT_DIR)

if {$env(wave)} {

    fsdbDumpfile "./${RESULT_DIR}/sim_${tc}_${seed}.fsdb"
    # "+mda"   - Include multi-dimensional arrays (Memory/Array)
    # "+struct" - Include structs (optional)
    fsdbDumpvars 0 tb_top +mda +struct
}
run 10ms
quit
