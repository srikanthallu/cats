[GlobalParams]
  dg_scheme = nipg
  sigma = 10
  Coefficient = 0.5
[] #END GlobalParams

[Problem]

    coord_type = RZ
    #NOTE: For RZ coordinates, x ==> R and y ==> Z (and z ==> nothing)

[] #END Problem

[Mesh]

    type = GeneratedMesh
    dim = 2
    nx = 1
    ny = 20
    xmin = 0.0
    xmax = 2.0    #2cm radius
    ymin = 0.0
    ymax = 5.0    #5cm length

[] # END Mesh

[Variables]

## ----- NOTE: Cross-Coupled Variables for Mass MUST have same order and family !!! ------- ##
    [./NH3]
        order = FIRST
        family = MONOMIAL
        initial_condition = 1e-10
    [../]

    [./q1]
        order = FIRST
        family = MONOMIAL
        initial_condition = 0
    [../]

    [./q2]
        order = FIRST
        family = MONOMIAL
        initial_condition = 0
    [../]

    [./q3]
        order = FIRST
        family = MONOMIAL
        initial_condition = 0
    [../]

    [./qT]
        order = FIRST
        family = MONOMIAL
        initial_condition = 0
    [../]

[] #END Variables

[AuxVariables]

  [./O2]
      order = FIRST
      family = MONOMIAL
      initial_condition = 5.35186739166803E-05
  [../]

  #MOVED water to AuxVariables because we don't want to consider mass transfer right now
  [./H2O]
      order = FIRST
      family = MONOMIAL
      initial_condition = 0.001337966847917
  [../]

  [./w1]
      order = FIRST
      family = MONOMIAL
      initial_condition = 0.05016
  [../]

  [./w2]
      order = FIRST
      family = MONOMIAL
      initial_condition = 0.03534
  [../]

  [./w3]
      order = FIRST
      family = MONOMIAL
      initial_condition = 0.03963
  [../]

  [./temp]
      order = FIRST
      family = MONOMIAL
      initial_condition = 423.15
  [../]

  [./Diff]
    order = FIRST
    family = MONOMIAL
    initial_condition = 75.0
  [../]
 
  [./Dz]
    order = FIRST
    family = MONOMIAL
    initial_condition = 0.0
  [../]

  [./pore]
      order = FIRST
      family = MONOMIAL
      initial_condition = 0.3309
  [../]

  [./vel_x]
      order = FIRST
      family = LAGRANGE
      initial_condition = 0
  [../]

  [./vel_y]
      order = FIRST
      family = LAGRANGE
      initial_condition = 7555.15
  [../]

  [./vel_z]
      order = FIRST
      family = LAGRANGE
      initial_condition = 0
  [../]

[] #END AuxVariables

[ICs]

[] #END ICs

[Kernels]

    [./NH3_dot]
        type = VariableCoefTimeDerivative
        variable = NH3
        coupled_coef = pore
    [../]
    [./NH3_gadv]
        type = GPoreConcAdvection
        variable = NH3
        porosity = pore
        ux = vel_x
        uy = vel_y
        uz = vel_z
    [../]
    [./NH3_gdiff]
        type = GVarPoreDiffusion
        variable = NH3
        porosity = pore
        Dx = Diff
        Dy = Diff
        Dz = Dz
    [../]
    [./transfer_qT]
      type = CoupledPorePhaseTransfer
      variable = NH3
      coupled = qT
      porosity = pore
    [../]

    [./q1_dot]
        type = CoefTimeDerivative
        variable = q1
    [../]
    [./q1_rxn]
      type = Reaction
      variable = q1
    [../]
#    [./q1_e]
#        type = BodyForce
#        variable = q1
#        value = 0.33
#    [../]
    [./q1_lang] #site 1
      type = VarSiteDensityExtLangModel
      variable = q1
      coupled_site_density = w1
      main_coupled = NH3
      coupled_list = 'NH3 H2O'
      enthalpies = '-60019.6 -25656.6'
      entropies = '-42.4329 -5.24228'
      coupled_temp = temp
    [../]

    [./q2_dot]
        type = CoefTimeDerivative
        variable = q2
    [../]
    [./q2_rxn]
      type = Reaction
      variable = q2
    [../]
#    [./q2_e]
#        type = BodyForce
#        variable = q2
#        value = 0.33
#    [../]
    [./q2_lang] #site 2
      type = VarSiteDensityExtLangModel
      variable = q2
     coupled_site_density = w2
      main_coupled = NH3
      coupled_list = 'NH3'
      enthalpies = '-77077.9'
      entropies = '-41.8576'
      coupled_temp = temp
    [../]

    [./q3_dot]
        type = CoefTimeDerivative
        variable = q3
    [../]
    [./q3_rxn]
      type = Reaction
      variable = q3
    [../]
#    [./q3_e]
#        type = BodyForce
#        variable = q3
#        value = 0.33
#    [../]
    [./q3_lang] #site 3
      type = VarSiteDensityExtLangModel
      variable = q3
      coupled_site_density = w3
      main_coupled = NH3
      coupled_list = 'NH3'
      enthalpies = '-78147'
      entropies = '-12.1126'
      coupled_temp = temp
    [../]

    [./qT_res]
      type = Reaction
      variable = qT
    [../]
    [./qT_sum]
      type = CoupledSumFunction
      variable = qT
      coupled_list = 'q1 q2 q3'
    [../]

    #[./H2O_dot]
    #    type = VariableCoefTimeDerivative
    #    variable = H2O
    #    coupled_coef = pore
    #[../]
    #[./H2O_gadv]
    #    type = GPoreConcAdvection
    #    variable = H2O
    #    porosity = pore
    #    ux = vel_x
    #    uy = vel_y
    #    uz = vel_z
    #[../]
    #[./H2O_gdiff]
    #    type = GVarPoreDiffusion
    #    variable = H2O
    #    porosity = pore
    #    Dx = Diff
    #    Dy = Diff
    #    Dz = Dz
    #[../]
    # ------------- NOTE: Ignoring H2O mass transfer for this test  --------------

[] #END Kernels

[DGKernels]

    [./NH3_dgadv]
        type = DGPoreConcAdvection
        variable = NH3
        porosity = pore
        ux = vel_x
        uy = vel_y
        uz = vel_z
    [../]
    [./NH3_dgdiff]
        type = DGVarPoreDiffusion
        variable = NH3
        porosity = pore
        Dx = Diff
        Dy = Diff
        Dz = Dz
    [../]

    #[./H2O_dgadv]
    #    type = DGPoreConcAdvection
    #    variable = H2O
    #    porosity = pore
    #    ux = vel_x
    #    uy = vel_y
    #    uz = vel_z
    #[../]
    #[./H2O_dgdiff]
    #    type = DGVarPoreDiffusion
    #    variable = H2O
    #    porosity = pore
    #    Dx = Diff
    #    Dy = Diff
    #    Dz = Dz
    #[../]

[] #END DGKernels

[AuxKernels]

[] #END AuxKernels

[BCs]

    [./NH3_FluxIn]
      type = DGPoreConcFluxStepwiseBC
      variable = NH3
      boundary = 'bottom'
      u_input = 1E-10
      porosity = pore
      ux = vel_x
      uy = vel_y
      uz = vel_z
      input_vals = '2.78862977563539E-05 1.40E-05'
      input_times = '2 4'
      time_spans = '0.25 0.25'
    [../]
    [./NH3_FluxOut]
      type = DGPoreConcFluxBC
      variable = NH3
      boundary = 'top'
      porosity = pore
      ux = vel_x
      uy = vel_y
      uz = vel_z
    [../]

    #[./H2O_FluxIn]
    #  type = DGPoreConcFluxBC
    #  variable = H2O
    #  boundary = 'bottom'
    #  u_input = 0.001337966847917
    #  porosity = pore
    #  ux = vel_x
    #  uy = vel_y
    #  uz = vel_z
    #[../]
    #[./H2O_FluxOut]
    #  type = DGPoreConcFluxBC
    #  variable = H2O
    #  boundary = 'top'
    #  porosity = pore
    #  ux = vel_x
    #  uy = vel_y
    #  uz = vel_z
    #[../]

[] #END BCs

[Materials]

[] #END Materials

[Postprocessors]

    [./NH3_exit]
        type = SideAverageValue
        boundary = 'top'
        variable = NH3
        execute_on = 'initial timestep_end'
    [../]
 
    [./NH3_enter]
        type = SideAverageValue
        boundary = 'bottom'
        variable = NH3
        execute_on = 'initial timestep_end'
    [../]

    [./q1_avg]
        type = ElementAverageValue
        variable = q1
        execute_on = 'initial timestep_end'
    [../]

    [./q2_avg]
        type = ElementAverageValue
        variable = q2
        execute_on = 'initial timestep_end'
    [../]

    [./q3_avg]
        type = ElementAverageValue
        variable = q3
        execute_on = 'initial timestep_end'
    [../]

    [./qT_avg]
        type = ElementAverageValue
        variable = qT
        execute_on = 'initial timestep_end'
    [../]

[] #END Postprocessors

[Preconditioning]
  [./SMP_PJFNK]
    type = SMP
    full = true
    solve_type = newton   #default to newton, but use pjfnk if newton too slow
  [../]
[] #END Preconditioning

[Executioner]
  type = Transient
  scheme = implicit-euler
  petsc_options = '-snes_converged_reason'
  petsc_options_iname ='-ksp_type -pc_type -sub_pc_type -snes_max_it -sub_pc_factor_shift_type -pc_asm_overlap -snes_atol -snes_rtol'
  petsc_options_value = 'gmres asm lu 100 NONZERO 2 1E-14 1E-12'

  #NOTE: turning off line search can help converge for high Renolds number
  line_search = bt 
  nl_rel_tol = 1e-6
  nl_abs_tol = 1e-4
  nl_rel_step_tol = 1e-10
  nl_abs_step_tol = 1e-10
  nl_max_its = 10
  l_tol = 1e-6
  l_max_its = 300

  start_time = 2.0
  end_time = 6.0
  dtmax = 0.5

  [./TimeStepper]
     type = ConstantDT
     dt = 0.25
  [../]
[] #END Executioner

[Outputs]
  print_linear_residuals = false
  exodus = true
  csv = true
[] #END Outputs
