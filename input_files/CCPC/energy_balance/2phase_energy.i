[GlobalParams]
    dg_scheme = nipg
    sigma = 10
  
[] #END GlobalParams

[Problem]
    #NOTE: For RZ coordinates, x ==> R and y ==> Z (and z ==> nothing)
    coord_type = RZ
[] #END Problem
 
[Mesh]
    type = GeneratedMesh
    dim = 2
    nx = 5
    ny = 10
    xmin = 0.0
    xmax = 0.0725    # m radius
    ymin = 0.0
    ymax = 0.1346    # m length
[]

[Variables]
    [./Ef]
        order = FIRST
        family = MONOMIAL
        # Ef = rho*cp*T     (1 kg/m^3) * (1000 J/kg/K) * (298 K)
        [./InitialCondition]
            type = InitialPhaseEnergy
            specific_heat = cpg
            volume_frac = eps
            density = rho
            temperature = Tf
        [../]
    [../]
 
    [./Es]
        order = FIRST
        family = MONOMIAL
        # Ef = rho*cp*T     (1 kg/m^3) * (1000 J/kg/K) * (298 K)
        [./InitialCondition]
            type = InitialPhaseEnergy
            specific_heat = cps
            volume_frac = s_frac
            density = rho_s
            temperature = Ts
        [../]
    [../]
 
    [./Tf]
        order = FIRST
        family = MONOMIAL
        initial_condition = 298  #K
    [../]
 
    [./Ts]
        order = FIRST
        family = MONOMIAL
        initial_condition = 298  #K
    [../]
 
    # Bulk gas concentration for O2
    [./O2]
        order = FIRST
        family = MONOMIAL
        initial_condition = 1e-9    #mol/m^3
    [../]
[]
 
[AuxVariables]
    [./vel_x]
        order = FIRST
        family = LAGRANGE
        initial_condition = 0
    [../]

    [./vel_y]
        order = FIRST
        family = LAGRANGE
        initial_condition = 2.5769 #m/s  - superficial velocity
    [../]

    [./vel_z]
        order = FIRST
        family = LAGRANGE
        initial_condition = 0
    [../]
 
    [./Kg]
        order = FIRST
        family = MONOMIAL
        initial_condition = 0.1          #W/m/K
    [../]
 
    [./Ks]
        order = FIRST
        family = MONOMIAL
        initial_condition = 11.9       #W/m/K
    [../]
 
    [./eps]
        order = FIRST
        family = MONOMIAL
        initial_condition = 0.4371          #W/m/K
    [../]
 
    [./s_frac]
        order = FIRST
        family = MONOMIAL
        initial_condition = 0.5629          #W/m/K
    [../]
 
    [./rho]
        order = FIRST
        family = MONOMIAL
        initial_condition = 1       #kg/m^3
    [../]
 
    [./rho_s]
        order = FIRST
        family = MONOMIAL
        initial_condition = 1599       #kg/m^3
    [../]
 
    [./cpg]
        order = FIRST
        family = MONOMIAL
        initial_condition = 1000       #J/kg/K
    [../]
 
    [./cps]
        order = FIRST
        family = MONOMIAL
        initial_condition = 680       #J/kg/K
    [../]
 
    [./hw]
        order = FIRST
        family = MONOMIAL
        initial_condition = 50       #W/m^2/K
    [../]
 
[]

[Kernels]
     [./Ef_dot]
         type = TimeDerivative
         variable = Ef
     [../]
     [./Ef_gadv]
         type = GPoreConcAdvection
         variable = Ef
         porosity = eps
         ux = vel_x
         uy = vel_y
         uz = vel_z
     [../]
     [./Ef_gdiff]
         type = GThermalConductivity
         variable = Ef
         temperature = Tf
         Dx = Kg
         Dy = Kg
         Dz = Kg
     [../]
 
    [./Tf_calc]
        type = PhaseTemperature
        variable = Tf
        energy = Ef
        specific_heat = cpg
        volume_frac = eps
        density = rho
    [../]
 
    [./O2_dot]
        type = VariableCoefTimeDerivative
        variable = O2
        coupled_coef = eps
    [../]
    [./O2_gadv]
        type = GPoreConcAdvection
        variable = O2
        porosity = eps
        ux = vel_x
        uy = vel_y
        uz = vel_z
    [../]
    [./O2_gdiff]
        type = GVarPoreDiffusion
        variable = O2
        porosity = eps
        Dx = 0.01
        Dy = 0.01
        Dz = 0.01
    [../]
[]
 
[DGKernels]
    [./Ef_dgadv]
        type = DGPoreConcAdvection
        variable = Ef
        porosity = eps
        ux = vel_x
        uy = vel_y
        uz = vel_z
    [../]
    [./Ef_dgdiff]
        type = DGThermalConductivity
        variable = Ef
        temperature = Tf
        Dx = Kg
        Dy = Kg
        Dz = Kg
    [../]
 
    [./O2_dgadv]
        type = DGPoreConcAdvection
        variable = O2
        porosity = eps
        ux = vel_x
        uy = vel_y
        uz = vel_z
    [../]
    [./O2_dgdiff]
        type = DGVarPoreDiffusion
        variable = O2
        porosity = eps
        Dx = 0.01
        Dy = 0.01
        Dz = 0.01
    [../]
[]

[BCs]
    [./Ef_FluxIn]
        type = DGPoreConcFluxBC
        variable = Ef
        u_input = 348000
        boundary = 'bottom'
        porosity = eps
        ux = vel_x
        uy = vel_y
        uz = vel_z
    [../]
    [./Ef_FluxOut]
        type = DGPoreConcFluxBC
        variable = Ef
        boundary = 'top'
        porosity = eps
        ux = vel_x
        uy = vel_y
        uz = vel_z
    [../]
 
    [./Ef_WallFluxIn]
        type = DGWallEnergyFluxBC
        variable = Ef
        boundary = 'right'
        transfer_coef = hw
        wall_temp = 323
        temperature = Tf
        area_frac = eps
    [../]
 
    [./O2_FluxIn]
        type = DGPoreConcFluxBC
        variable = O2
        boundary = 'bottom'
        u_input = 1e-6
        porosity = eps
        ux = vel_x
        uy = vel_y
        uz = vel_z
    [../]
    [./O2_FluxOut]
        type = DGPoreConcFluxBC
        variable = O2
        boundary = 'top'
        porosity = eps
        ux = vel_x
        uy = vel_y
        uz = vel_z
    [../]

[]

[Postprocessors]
    [./Ef_out]
        type = SideAverageValue
        boundary = 'top'
        variable = Ef
        execute_on = 'initial timestep_end'
    [../]
 
    [./Ef_in]
        type = SideAverageValue
        boundary = 'bottom'
        variable = Ef
        execute_on = 'initial timestep_end'
    [../]
 
    [./T_out]
        type = SideAverageValue
        boundary = 'top'
        variable = Tf
        execute_on = 'initial timestep_end'
    [../]
 
    [./T_in]
        type = SideAverageValue
        boundary = 'bottom'
        variable = Tf
        execute_on = 'initial timestep_end'
    [../]
 
    [./O2_out]
        type = SideAverageValue
        boundary = 'top'
        variable = O2
        execute_on = 'initial timestep_end'
    [../]
 
    [./O2_in]
        type = SideAverageValue
        boundary = 'bottom'
        variable = O2
        execute_on = 'initial timestep_end'
    [../]
[]

[Preconditioning]
  [./SMP_PJFNK]
    type = SMP
    full = true
    solve_type = pjfnk   #default to newton, but use pjfnk if newton too slow
  [../]
[] #END Preconditioning

[Executioner]
  type = Transient
  scheme = implicit-euler
  petsc_options = '-snes_converged_reason'
  petsc_options_iname ='-ksp_type -pc_type -sub_pc_type -snes_max_it -sub_pc_factor_shift_type -pc_asm_overlap -snes_atol -snes_rtol'
  petsc_options_value = 'gmres lu ilu 100 NONZERO 2 1E-14 1E-12'

  #NOTE: turning off line search can help converge for high Renolds number
  line_search = none
  nl_rel_tol = 1e-6
  nl_abs_tol = 1e-4
  nl_rel_step_tol = 1e-10
  nl_abs_step_tol = 1e-10
  nl_max_its = 10
  l_tol = 1e-6
  l_max_its = 300

  start_time = 0.0
  end_time = 0.5
  dtmax = 0.25

  [./TimeStepper]
     type = ConstantDT
     dt = 0.05
  [../]
[] #END Executioner

[Outputs]
  print_linear_residuals = true
  exodus = true
  csv = true
[] #END Outputs

