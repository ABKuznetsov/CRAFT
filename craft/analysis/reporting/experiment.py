"""Publication fields from coreCIF and pdCIF, without inferring an experiment.

Sources: IUCr coreCIF required items and pdCIF required items:
https://iucrdata.iucr.org/services/cif/reqditems.html
https://journals.iucr.org/e/services/pd_reqditems.html
"""

from craft.analysis.reporting.model import Availability, Provenance, ReportCell, ReportColumn, ReportRow, ReportTable


# Source order is not the order of a publication table. Keep related fields
# together and retain the actual source tag on each value, including loop data.
_FIELDS = (
    ("_exptl_method", "Experimental method"),
    ("_diffrn_ambient_temperature", "Temperature (K)"),
    ("_diffrn_ambient_pressure", "Pressure (kPa)"),
    ("_diffrn_measurement_device", "Instrument"),
    ("_diffrn_measurement_device_type", "Instrument model"),
    ("_diffrn_measurement_method", "Collection method"),
    ("_diffrn_detector", "Detector"),
    ("_diffrn_detector_type", "Detector model"),
    ("_diffrn_radiation_probe", "Radiation probe"),
    ("_diffrn_source", "Radiation source"),
    ("_diffrn_source_type", "Source model"),
    ("_diffrn_radiation_source", "Radiation source description"),
    ("_diffrn_radiation_type", "Radiation"),
    ("_diffrn_radiation_wavelength", "Wavelength (Å)"),
    ("_diffrn_radiation_wavelength_wt", "Wavelength relative weight"),
    ("_diffrn_radiation_monochromator", "Monochromator"),
    ("_exptl_crystal_description", "Crystal habit"),
    ("_exptl_crystal_colour", "Crystal colour"),
    ("_exptl_crystal_size_max", "Crystal size maximum (mm)"),
    ("_exptl_crystal_size_mid", "Crystal size intermediate (mm)"),
    ("_exptl_crystal_size_min", "Crystal size minimum (mm)"),
    ("_exptl_crystal_density_diffrn", "Calculated density (Mg m⁻³)"),
    ("_exptl_crystal_f_000", "F(000)"),
    ("_exptl_absorpt_coefficient_mu", "Absorption coefficient μ (mm⁻¹)"),
    ("_exptl_absorpt_correction_type", "Absorption correction"),
    ("_exptl_absorpt_process_details", "Absorption correction details"),
    ("_exptl_absorpt_correction_t_min", "Minimum transmission factor"),
    ("_exptl_absorpt_correction_t_max", "Maximum transmission factor"),
    ("_diffrn_reflns_theta_min", "θ minimum (°)"),
    ("_diffrn_reflns_theta_max", "θ maximum (°)"),
    *((f"_diffrn_reflns_limit_{axis}_{limit}", f"{axis} {label}")
      for axis in "hkl" for limit, label in (("min", "minimum"), ("max", "maximum"))),
    ("_diffrn_reflns_number", "Measured reflections"),
    ("_reflns_number_total", "Independent reflections"),
    ("_reflns_number_gt", "Observed reflections"),
    ("_reflns_threshold_expression", "Observation threshold"),
    ("_diffrn_reflns_av_r_equivalents", "Rint"),
    ("_diffrn_reflns_av_unet_i/net_i", "Rσ"),
    ("_diffrn_measured_fraction_theta_max", "Completeness at θ maximum"),
    ("_pd_instr_geometry", "Instrument geometry"),
    ("_pd_instr_location", "Instrument location"),
    ("_pd_spec_description", "Specimen description"),
    ("_pd_spec_preparation", "Specimen preparation"),
    ("_pd_spec_mounting", "Specimen holder"),
    ("_pd_spec_mount_mode", "Reflection / transmission geometry"),
    ("_pd_spec_shape", "Specimen shape"),
    ("_pd_char_particle_morphology", "Particle size and morphology"),
    ("_pd_meas_scan_method", "Scan method"),
    ("_pd_meas_2theta_range_min", "2θ minimum (°)"),
    ("_pd_meas_2theta_range_max", "2θ maximum (°)"),
    ("_pd_meas_2theta_range_inc", "2θ step (°)"),
    ("_pd_meas_2theta_fixed", "Fixed 2θ (°)"),
    ("_pd_meas_step_count_time", "Counting time per point (s)"),
    ("_pd_meas_number_of_points", "Measured pattern points"),
    ("_pd_meas_special_details", "Measurement details"),
    ("_pd_proc_2theta_range_min", "Processed 2θ minimum (°)"),
    ("_pd_proc_2theta_range_max", "Processed 2θ maximum (°)"),
    ("_pd_proc_2theta_range_inc", "Processed 2θ step (°)"),
    ("_pd_proc_wavelength", "Processed wavelength (Å)"),
    ("_pd_proc_number_of_points", "Processed pattern points"),
    ("_pd_proc_info_excluded_regions", "Excluded profile regions"),
    ("_pd_proc_ls_profile_function", "Profile function"),
    ("_pd_proc_ls_background_function", "Background function"),
    ("_pd_proc_ls_pref_orient_corr", "Preferred orientation correction"),
    ("_pd_proc_ls_prof_r_factor", "Profile R factor"),
    ("_pd_proc_ls_prof_wr_factor", "Weighted profile R factor"),
    ("_pd_proc_ls_prof_wr_expected", "Expected weighted profile R factor"),
    ("_refine_ls_structure_factor_coef", "Refined structure factor quantity"),
    ("_refine_ls_matrix_type", "Least-squares matrix"),
    ("_refine_ls_weighting_scheme", "Weighting scheme"),
    ("_refine_ls_number_reflns", "Reflections used in refinement"),
    ("_refine_ls_number_parameters", "Refined parameters"),
    ("_refine_ls_number_restraints", "Restraints"),
    ("_refine_ls_number_constraints", "Constraints"),
    ("_refine_ls_r_factor_all", "R (all reflections)"),
    ("_refine_ls_r_factor_gt", "R (observed reflections)"),
    ("_refine_ls_wr_factor_ref", "Weighted R (refinement set)"),
    ("_refine_ls_wr_factor_gt", "Weighted R (observed reflections)"),
    ("_refine_ls_wr_factor_all", "Weighted R (all reflections)"),
    ("_refine_ls_r_fsqd_factor", "R(F²)"),
    ("_refine_ls_r_i_factor", "R(I)"),
    ("_refine_ls_goodness_of_fit_ref", "Goodness of fit (refinement set)"),
    ("_refine_ls_goodness_of_fit_gt", "Goodness of fit (observed reflections)"),
    ("_refine_ls_hydrogen_treatment", "Hydrogen atom treatment"),
    ("_refine_ls_shift/su_max", "Maximum shift / standard uncertainty"),
    ("_refine_diff_density_max", "Residual density maximum (e/Å³)"),
    ("_refine_diff_density_min", "Residual density minimum (e/Å³)"),
    ("_refine_ls_abs_structure_flack", "Flack parameter"),
    ("_computing_data_collection", "Data collection software"),
    ("_computing_cell_refinement", "Cell refinement software"),
    ("_computing_data_reduction", "Data reduction software"),
    ("_computing_structure_solution", "Structure solution software"),
    ("_computing_structure_refinement", "Structure refinement software"),
)


def _key(tag):
    return tag.casefold().replace(".", "_")


def _reported_values(source):
    values = {}
    for tag, raw in source.scalars.items():
        if raw.strip() not in ("", "?", "."):
            values[_key(tag)] = (tag, (raw,))
    fields = {tag for tag, _label in _FIELDS}
    for loop in source.loops:
        for index, tag in enumerate(loop.tags):
            key = _key(tag)
            if key not in fields or key in values:
                continue
            reported = tuple(dict.fromkeys(row[index] for row in loop.rows
                                            if row[index].strip() not in ("", "?", ".")))
            if reported:
                values[key] = tag, reported
    return values


def build_refinement_table(structure):
    source = structure.source_data
    values = _reported_values(source)
    tags = {_key(tag) for tag in source.scalars}
    tags.update(_key(tag) for loop in source.loops for tag in loop.tags)
    # A phase name in a structure export is not evidence of powder collection.
    powder = any(tag.startswith(("_pd_meas_", "_pd_instr_", "_pd_proc_")) for tag in tags)
    single = any(tag.startswith(("_diffrn_reflns_", "_reflns_", "_exptl_crystal_size_")) for tag in values)
    title = ("Powder diffraction experiment and refinement" if powder else
             "Single-crystal experiment and refinement" if single else "Diffraction experiment and refinement")
    rows = []
    for key, label in _FIELDS:
        if key not in values:
            continue
        tag, reported = values[key]
        display = "; ".join(reported) if len(reported) <= 8 else "Variable; see source CIF"
        rows.append(ReportRow(f"refine:{tag}", {
            "parameter": ReportCell(label, label, Provenance.REPORTED, source_name=tag),
            "value": ReportCell("\n".join(reported), display,
                                Provenance.REPORTED, source_name=tag),
        }))
    return ReportTable("refinement", title,
        (ReportColumn("parameter", "Parameter"), ReportColumn("value", "Value")), tuple(rows),
        availability=Availability.AVAILABLE if rows else Availability.UNAVAILABLE,
        unavailable_reason="" if rows else "No experiment or refinement conditions are reported in the source CIF.",
        method="Reported coreCIF / pdCIF experiment and refinement conditions. Unreported values are omitted; measurement arrays are not reproduced.")
