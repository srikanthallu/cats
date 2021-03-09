'''
    This file creates an object to simulate isothermal monolith catalysis
    systems in pyomo. The primary objective of this simulator is to be
    used in conjunction with dynamic/kinetic monolith data and simulate
    that system while optimizing for the reactions in the system. User must
    provide some reasonable initial guesses to the kinetic parameters for
    the model to work effectively.

    Author:     Austin Ladshaw
    Date:       03/02/2021
    Copyright:  This kernel was designed and built at Oak Ridge National
                Laboratory by Austin Ladshaw for research in the area
                of adsorption, catalysis, and surface science.
'''

# Import the pyomo environments
from pyomo.environ import *
from pyomo.dae import *

# Other import statements
import yaml
import os.path
from os import path
from enum import Enum

# Define an Enum class for reaction types
class ReactionType(Enum):
    Arrhenius = 1
    EquilibriumArrhenius = 2

# Define an Enum class for discretizer types
class DiscretizationMethod(Enum):
    OrthogonalCollocation = 1
    FiniteDifference = 2

# Helper function for Arrhenius reaction rates
#   E = activation energy in J/mol
#   A = pre-exponential factor (units depend on reaction)
#   B = power of temperature (usually = 0)
#   T = temperature of system in K
#
#   Function returns the k value of the Arrhenius Expression
def arrhenius_rate_const(A, B, E, T):
    return A*T**B*exp(-E/8.3145/T)

# Helper function for Equilibrium Arrhenius reaction rates
#   Af = forward rate pre-exponential term (units depend on reaction)
#   Ef = forward rate activation energy in J/mol
#   dH = equilibrium reaction enthalpy in J/mol
#   dS = equilibrium reaction entropy in J/K/mol
#
#   Function returns a tuple of reverse pre-exponential and activation energy
#           (Ar, Er)
def equilibrium_arrhenius_consts(Af, Ef, dH, dS):
    Ar = Af*exp(-dS/8.3145)
    Er = Ef - dH
    return (Ar, Er)


# Class object to hold the simulator and all model components
#       This object will be how a user interfaces with the
#       pyomo simulator and dictates the form of the model
#
#       Generalized Model Form:
#       ----------------------
#
#           Mass balance in channel space (Mandatory)
#
#                   eb*dCb/dt + eb*v*dCb/dz = -Ga*km*(Cb - C)
#
#           Mass balance in the washcoat (Mandatory)
#
#                   ew*(1-eb)*dC/dt = Ga*km*(Cb - C) + (1-eb)*SUM(all i, u_ci * ri)
#
#           Surface species reaction terms (Optional, if surface species not needed)
#
#                   dq/dt = SUM(all i, u_qi * ri)
#
#           Specific Site Balances (Optional, but required if tracking surface species)
#
#                   Smax = S + SUM(all qi, u_si*qi) = 0
#
class Isothermal_Monolith_Simulator(object):
    #Default constructor
    # Pass a list of species names (Specs) for the mass balances
    def __init__(self):
        # Create an empty concrete model
        self.model = ConcreteModel()

        # Add the mandatory components to the model
        #       TODO:     (?) Make all parameters into Var objects (?)
        self.model.eb = Param(within=NonNegativeReals, initialize=0.3309, mutable=True, units=None)
        self.model.ew = Param(within=NonNegativeReals, initialize=0.2, mutable=True, units=None)
        self.model.v = Param(within=Reals, initialize=15110, mutable=True, units=units.cm/units.min)
        self.model.km = Param(within=NonNegativeReals, initialize=1.12, mutable=True, units=units.m/units.min)
        self.model.Ga = Param(within=NonNegativeReals, initialize=5757.541, mutable=True, units=units.m**-1)

        # Add some tracking boolean statements
        self.isBoundsSet = False
        self.isTimesSet = False
        self.isTempSet = False
        self.temp_list = {}
        self.isAgeSet = False
        self.age_list = {}
        self.isGasSpecSet = False
        self.gas_list = {}
        self.isSurfSpecSet = False
        self.surf_list = {}
        self.isSitesSet = False
        self.site_list = {}
        self.isRxnSet = False
        self.isRxnBuilt = False
        self.rxn_list = {}
        self.isConBuilt = False
        self.isDiscrete = False
        self.isInitialSet = {}
        self.isBoundarySet = {}
        self.isObjectiveSet = False

    # Add a continuous set for spatial dimension (current expected units = cm)
    def add_axial_dim(self, start_point, end_point, point_list=[]):
        if point_list == []:
            self.model.z = ContinuousSet(bounds=(start_point,end_point))
        else:
            self.model.z = ContinuousSet(initialize=point_list)
        self.isBoundsSet = True

    # Add a continuous set for temporal dimension (current expected units = min)
    def add_temporal_dim(self, start_point, end_point, point_list=[]):
        if point_list == []:
            self.model.t = ContinuousSet(bounds=(start_point,end_point))
        else:
            self.model.t = ContinuousSet(initialize=point_list)
        self.isTimesSet = True


    # Add a param set for aging times/conditions [Can be reals, ints, or strings]
    #
    #       Access to model.age param is as follows:
    #       ---------------------------------------
    #           model.age[age, time] =
    #                       catalyst age at simulation time
    def add_age_set(self, ages):
        if self.isTimesSet == False:
            print("Error! Time dimension must be set first!")
            exit()

        if type(ages) is list:
            i=0
            for item in ages:
                key = "age_"+str(i)
                self.age_list[key] = item
                i+=1
            self.model.age_set = Set(initialize=ages)
            self.model.age = Param(self.model.age_set, self.model.t,
                                within=Any, mutable=True, units=None)
            for age in self.model.age_set:
                for time in self.model.t:
                    self.model.age[age, time].set_value(age)
        else:
            self.age_list["age_0"] = ages
            self.model.age_set = Set(initialize=[ages])
            self.model.age = Param(self.model.age_set, self.model.t,
                                    within=Any, mutable=True, units=units.K)
            for age in self.model.age_set:
                for time in self.model.t:
                    self.model.age[age, time].set_value(age)

        self.isAgeSet = True

    # Add a param set for isothermal temperatures [Must be reals]
    #       Currently expects temperatures in K
    #
    #       Access to model.T param is as follows:
    #       ---------------------------------------
    #           model.T[age, temperature, time] =
    #                       isothermal temperature for aging condition at simulation time
    def add_temperature_set(self, temps):
        if self.isTimesSet == False:
            print("Error! Time dimension must be set first!")
            exit()

        if self.isAgeSet == False:
            print("Error! Catalyst ages must be set first!")
            exit()

        if type(temps) is list:
            self.model.T_set = Set(initialize=temps)
            self.model.T = Param(self.model.age_set, self.model.T_set, self.model.t,
                                domain=NonNegativeReals, mutable=True, units=units.K)
            for age in self.model.age_set:
                for temperature in self.model.T_set:
                    for time in self.model.t:
                        self.model.T[age, temperature, time].set_value(298)
        else:
            self.model.T_set = Set(initialize=[temps])
            self.model.T = Param(self.model.age_set, self.model.T_set, self.model.t,
                                        domain=NonNegativeReals, mutable=True, units=units.K)
            for age in self.model.age_set:
                for temperature in self.model.T_set:
                    for time in self.model.t:
                        self.model.T[age, temperature, time].set_value(298)
        self.isTempSet = True

    # Add gas species (both bulk and washcoat) [Must be strings]
    #       Currently expects species concentrations in mol/L
    #
    #       Access to model.Cb and model.C Vars is as follows:
    #       ---------------------------------------
    #           model.Cb( or model.C )[species, age, temperature, location, time] =
    #                       bulk/pore concentration of given species, at given
    #                       aging condition, at given temperature, at given
    #                       axial location, at given simulation time
    #
    #       Access to model.Cb_in Param is as follows:
    #       ---------------------------------------
    #           model.Cb_in[species, age, temperature, time] =
    #                       bulk concentration of given species, at given
    #                       aging condition, at given temperature, at given
    #                       simulation time
    def add_gas_species(self, gas_species):
        if self.isTimesSet == False or self.isBoundsSet == False:
            print("Error! Cannot specify gas species until the time and bounds are set")
            exit()
        if self.isTempSet == False or self.isAgeSet == False:
            print("Error! Cannot specify gas species until the temperatures and ages are set")
            exit()

        if type(gas_species) is list:
            for item in gas_species:
                if isinstance(item, str):
                    self.gas_list[item] = {"bulk": item+"_b",
                                            "washcoat": item+"_w",
                                            "inlet": item+"_in"}
                else:
                    print("Error! Gas species must be a string")
                    exit()
            self.model.gas_set = Set(initialize=gas_species)
            self.model.Cb = Var(self.model.gas_set, self.model.age_set, self.model.T_set,
                            self.model.z, self.model.t,
                            domain=NonNegativeReals, bounds=(1e-20,1e5),
                            initialize=1e-20, units=units.mol/units.L)
            self.model.C = Var(self.model.gas_set, self.model.age_set, self.model.T_set,
                            self.model.z, self.model.t,
                            domain=NonNegativeReals, bounds=(1e-20,1e5),
                            initialize=1e-20, units=units.mol/units.L)
            self.model.Cb_in = Param(self.model.gas_set, self.model.age_set, self.model.T_set,
                            self.model.t,
                            within=NonNegativeReals, initialize=1e-20,
                            mutable=True, units=units.mol/units.L)
        else:
            if isinstance(gas_species, str):
                self.gas_list[gas_species] = {"bulk": gas_species+"_b",
                                            "washcoat": gas_species+"_w",
                                            "inlet": gas_species+"_in"}
                self.model.gas_set = Set(initialize=[gas_species])
                self.model.Cb = Var(self.model.gas_set, self.model.age_set, self.model.T_set,
                                self.model.z, self.model.t,
                                domain=NonNegativeReals, bounds=(1e-20,1e5),
                                initialize=1e-20, units=units.mol/units.L)
                self.model.C = Var(self.model.gas_set, self.model.age_set, self.model.T_set,
                                self.model.z, self.model.t,
                                domain=NonNegativeReals, bounds=(1e-20,1e5),
                                initialize=1e-20, units=units.mol/units.L)
                self.model.Cb_in = Param(self.model.gas_set, self.model.age_set, self.model.T_set,
                                self.model.t,
                                within=NonNegativeReals, initialize=1e-20,
                                mutable=True, units=units.mol/units.L)
            else:
                print("Error! Gas species must be a string")
                exit()
        self.isGasSpecSet = True
        for spec in self.model.gas_set:
            self.isBoundarySet[spec] = False
        self.model.dCb_dz = DerivativeVar(self.model.Cb, wrt=self.model.z, initialize=0, units=units.mol/units.L/units.min)
        self.model.dCb_dt = DerivativeVar(self.model.Cb, wrt=self.model.t, initialize=0, units=units.mol/units.L/units.min)
        self.model.dC_dt = DerivativeVar(self.model.C, wrt=self.model.t, initialize=0, units=units.mol/units.L/units.min)

    # Add surface species (optional) [Must be strings]
    #       Currently expects surface concentrations in mol/L
    #
    #       Access to model.q Vars is as follows:
    #       ---------------------------------------
    #           model.q[species, age, temperature, location, time] =
    #                       surface concentration of given species, at given
    #                       aging condition, at given temperature, at given
    #                       axial location, at given simulation time
    def add_surface_species(self, surf_species):
        if self.isGasSpecSet == False:
            print("Error! Cannot specify surface species without having gas species")
            exit()
        if type(surf_species) is list:
            for item in surf_species:
                if isinstance(item, str):
                    self.surf_list[item] = item
                else:
                    print("Error! Surface species must be a string")
                    exit()
            self.model.surf_set = Set(initialize=surf_species)
            self.model.q = Var(self.model.surf_set, self.model.age_set, self.model.T_set,
                            self.model.z, self.model.t,
                            domain=NonNegativeReals, bounds=(1e-20,1e5),
                            initialize=1e-20, units=units.mol/units.L)
        else:
            if isinstance(surf_species, str):
                self.surf_list[surf_species] = surf_species
                self.model.surf_set = Set(initialize=[surf_species])
                self.model.q = Var(self.model.surf_set, self.model.age_set, self.model.T_set,
                                self.model.z, self.model.t,
                                domain=NonNegativeReals, bounds=(1e-20,1e5),
                                initialize=1e-20, units=units.mol/units.L)
            else:
                print("Error! Surface species must be a string")
                exit()
        self.isSurfSpecSet = True
        self.model.dq_dt = DerivativeVar(self.model.q, wrt=self.model.t, initialize=0, units=units.mol/units.L/units.min)

    # Add surface sites (optional, but necessary when using surface species) [Must be strings]
    #       Currently expects surface concentrations in mol/L
    #
    #       Access to model.S Vars is as follows:
    #       ---------------------------------------
    #           model.S[site, age, temperature, location, time] =
    #                       surface concentration of given site, at given
    #                       aging condition, at given temperature, at given
    #                       axial location, at given simulation time
    #
    #       Access to model.Smax Param is as follows:
    #       ---------------------------------------
    #           model.Smax[site, age, location, time] =
    #                       maximum concentration of given site, at given
    #                       aging condition, at given temperature, at given
    #                       axial location, at given simulation time
    def add_surface_sites(self, sites):
        if self.isSurfSpecSet == False:
            print("Error! Cannot specify surface sites without having surface species")
            exit()
        if type(sites) is list:
            for item in sites:
                if isinstance(item, str):
                    self.site_list[item] = item
                else:
                    print("Error! Surface site must be a string")
                    exit()
            self.model.site_set = Set(initialize=sites)
            self.model.S = Var(self.model.site_set, self.model.age_set, self.model.T_set,
                            self.model.z, self.model.t,
                            domain=NonNegativeReals, bounds=(1e-20,1e5),
                            initialize=1e-20, units=units.mol/units.L)
            self.model.Smax = Param(self.model.site_set, self.model.age_set,
                            self.model.z, self.model.t,
                            within=NonNegativeReals, initialize=1e-20,
                            mutable=True, units=units.mol/units.L)
        else:
            if isinstance(sites, str):
                self.site_list[sites] = sites
                self.model.site_set = Set(initialize=[sites])
                self.model.S = Var(self.model.site_set, self.model.age_set, self.model.T_set,
                                self.model.z, self.model.t,
                                domain=NonNegativeReals, bounds=(1e-20,1e5),
                                initialize=1e-20, units=units.mol/units.L)
                self.model.Smax = Param(self.model.site_set, self.model.age_set,
                                self.model.z, self.model.t,
                                within=NonNegativeReals, initialize=1e-20,
                                mutable=True, units=units.mol/units.L)
            else:
                print("Error! Surface sites must be a string")
                exit()

        self.model.u_S = Param(self.model.site_set, self.model.surf_set, domain=Reals,
                                        initialize=0, mutable=True)
        self.isSitesSet = True

    # Add reactions to the model (does not include molar contributions to mass balances yet)
    #       Currently expects Arrhenius rate terms as the following...
    #           A = pre-exponential term (units depend on reaction type)
    #           E = activation energy in J/mol
    #           B = temperature power (no units, optional)
    #           dH = reaction enthalpy (J/mol) - for equilibrium
    #           dS = reaction entropy (J/K/mol) - for equilibrium
    #
    #   NOTE: The 'rxns' argument must be a dictionary whose keys are the labels or names
    #           of the reactions to consider and that maps to a type of reaction we
    #           want to create for that label
    def add_reactions(self, rxns):
        if self.isGasSpecSet == False:
            print("Error! Cannot specify reactions before defining species")
            exit()

        if type(rxns) is not dict:
            print("Error! Must specify reactions using a formatted dictionary")
            exit()

        # Iterate through the reaction list
        arr_rxn_list = []
        arr_equ_rxn_list = []
        full_rxn_list = []
        for r in rxns:
            full_rxn_list.append(r)
            # Determine what to do with different reaction types
            if rxns[r] == ReactionType.Arrhenius:
                arr_rxn_list.append(r)
            elif rxns[r] == ReactionType.EquilibriumArrhenius:
                arr_equ_rxn_list.append(r)
            else:
                print("Error! Unsupported 'ReactionType' object")
                exit()

        # Setup model with all reactions (store sets for each type)
        self.model.all_rxns = Set(initialize=full_rxn_list)
        self.model.arrhenius_rxns = Set(initialize=arr_rxn_list)
        self.model.equ_arrhenius_rxns = Set(initialize=arr_equ_rxn_list)

        # All reactions (regardless of type) have some impact on mass balances
        #           Access is [species, rxn, loc]
        #
        #       NOTE: u_C and u_q were made positional so that reactions could be
        #           turned off or on based on location in the domain. This can be
        #           utilized to simulate the effect of catalyst 'zoning'
        self.model.u_C = Param(self.model.gas_set, self.model.all_rxns, self.model.z, domain=Reals,
                                initialize=0, mutable=True)
        if self.isSurfSpecSet == True:
            self.model.u_q = Param(self.model.surf_set, self.model.all_rxns, self.model.z, domain=Reals,
                                    initialize=0, mutable=True)

        # Variables for the Arrhenius type
        self.model.A = Var(self.model.arrhenius_rxns, domain=NonNegativeReals, initialize=0)
        self.model.B = Var(self.model.arrhenius_rxns, domain=Reals, initialize=0)
        self.model.E = Var(self.model.arrhenius_rxns, domain=Reals, initialize=0)

        # Variables for the Equilibrium Arrhenius type
        self.model.Af = Var(self.model.equ_arrhenius_rxns, domain=NonNegativeReals, initialize=0)
        self.model.Ef = Var(self.model.equ_arrhenius_rxns, domain=Reals, initialize=0)
        self.model.dH = Var(self.model.equ_arrhenius_rxns, domain=Reals, initialize=0)
        self.model.dS = Var(self.model.equ_arrhenius_rxns, domain=Reals, initialize=0)

        full_species_list = []
        for gas in self.model.gas_set:
            full_species_list.append(gas)
        if self.isSurfSpecSet == True:
            for surf in self.model.surf_set:
                full_species_list.append(surf)
            if self.isSitesSet == True:
                for site in self.model.site_set:
                    full_species_list.append(site)

        self.model.all_species_set = Set(initialize=full_species_list)
        for spec in self.model.all_species_set:
            self.isInitialSet[spec] = False
        #       Access is [rxn, species]
        self.model.rxn_orders = Param(self.model.all_rxns, self.model.all_species_set,
                                    domain=Reals, initialize=0, mutable=True)
        self.isRxnSet = True
        for rxn in rxns:
            self.rxn_list[rxn] = {}
            self.rxn_list[rxn]["type"]=rxns[rxn]
            self.rxn_list[rxn]["fixed"]=False


    #========= Setup functions for parameters ===============
    def set_bulk_porosity(self, eb):
        if eb > 1 or eb < 0:
            print("Error! Porosity must be a value between 0 and 1")
            exit()
        self.model.eb.set_value(eb)

    def set_washcoat_porosity(self, ew):
        if ew > 1 or ew < 0:
            print("Error! Porosity must be a value between 0 and 1")
            exit()
        self.model.ew.set_value(ew)

    def set_linear_velocity(self, v):
        self.model.v.set_value(v)

    def set_mass_transfer_coef(self, km):
        self.model.km.set_value(km)

    def set_surface_to_volume_ratio(self, Ga):
        self.model.Ga.set_value(Ga)

    # Site density is a function of aging, thus you provide the
    #       name of the site you want to set and the age that the
    #       given value would correspond to
    def set_site_density(self, site, age, value):
        if self.isSitesSet == False:
            print("Error! Did not specify the existance of surface sites")
            exit()
        if value < 0:
            print("Error! Cannot have a negative concentration of sites")
            exit()
        if value < 1e-20:
            value = 1e-20
        for loc in self.model.z:
            for time in self.model.t:
                self.model.Smax[site, age, loc, time].set_value(value)

    # Set the isothermal temperatures for a simulation
    #   Sets all to a constant, can be changed later
    def set_isothermal_temp(self,age,temp,value):
        for time in self.model.t:
            self.model.T[age,temp,time].set_value(value)

    # Setup site balance information (in needed)
    #       To setup the information for a site balance, pass the name of the
    #       site (site) you want to specify, then pass a dictionary containing
    #       relevant site balance information
    def set_site_balance(self, site, info):
        if self.isSitesSet == False:
            print("Error! Cannot set site balance info before specifying that there are sites")
            exit()
        if type(info) is not dict:
            print("Error! Must specify site balances using a formatted dictionary")
            exit()
        if "mol_occupancy" not in info:
            print("Error! Must specify reaction 'mol_occupancy' in dictionary")
            exit()
        for spec in self.model.surf_set:
            if spec in info["mol_occupancy"]:
                self.model.u_S[site, spec].set_value(info["mol_occupancy"][spec])


    # Setup reaction information
    #       To setup information for a reaction, pass the name of the
    #       reaction (rxn) you want to specify and then pass a dictionary
    #       containing relevant reaction information.
    #
    #
    def set_reaction_info(self, rxn, info):
        if self.isRxnSet == False:
            print("Error! Cannot set reaction parameters before declaring reaction types")
            exit()
        if type(info) is not dict:
            print("Error! Must specify reactions using a formatted dictionary")
            exit()
        if "parameters" not in info:
            print("Error! Must specify reaction 'parameters' in dictionary")
            exit()
        if "mol_reactants" not in info:
            print("Error! Must specify reaction 'mol_reactants' in dictionary")
            exit()
        if "mol_products" not in info:
            print("Error! Must specify reaction 'mol_products' in dictionary")
            exit()
        if "rxn_orders" not in info:
            print("Error! Must specify reaction 'rxn_orders' in dictionary")
            exit()
        if rxn in self.model.arrhenius_rxns:
            self.model.A[rxn].set_value(info["parameters"]["A"])
            self.model.E[rxn].set_value(info["parameters"]["E"])
            try:
                self.model.B[rxn].set_value(info["parameters"]["B"])
            except:
                self.model.B[rxn].set_value(0)
                self.model.B[rxn].fix()
        elif rxn in self.model.equ_arrhenius_rxns:
            self.model.Af[rxn].set_value(info["parameters"]["A"])
            self.model.Ef[rxn].set_value(info["parameters"]["E"])
            self.model.dH[rxn].set_value(info["parameters"]["dH"])
            self.model.dS[rxn].set_value(info["parameters"]["dS"])
        else:
            print("Error! Given reaction name does not exist in model")
            exit()

        #Create a model set for reactants and products
        react_list = []
        prod_list = []
        for spec in self.model.all_species_set:
            if spec in info["mol_reactants"]:
                react_list.append(spec)
            if spec in info["mol_products"]:
                prod_list.append(spec)

        # Add sets for reactants and products specific to each reaction
        self.model.add_component(rxn+"_reactants", Set(initialize=react_list))
        self.model.add_component(rxn+"_products", Set(initialize=prod_list))

        # Grab all stoichiometry information
        for spec in self.model.gas_set:
            u_C_sum = 0
            if spec in info["mol_reactants"]:
                u_C_sum -= info["mol_reactants"][spec]
            if spec in info["mol_products"]:
                u_C_sum += info["mol_products"][spec]
            for loc in self.model.z:
                self.model.u_C[spec,rxn,loc].set_value(u_C_sum)

        if self.isSurfSpecSet == True:
            for spec in self.model.surf_set:
                u_q_sum = 0
                if spec in info["mol_reactants"]:
                    u_q_sum -= info["mol_reactants"][spec]
                if spec in info["mol_products"]:
                    u_q_sum += info["mol_products"][spec]
                for loc in self.model.z:
                    self.model.u_q[spec,rxn,loc].set_value(u_q_sum)

        # Set reaction order information
        for spec in self.model.all_species_set:
            if spec in info["rxn_orders"]:
                if spec in info["mol_reactants"] or spec in info["mol_products"]:
                    self.model.rxn_orders[rxn,spec].set_value(info["rxn_orders"][spec])

        self.isRxnBuilt = True

    # Define a single arrhenius rate function to be used in the model
    #       This function assumes the reaction index (rxn) is valid
    def arrhenius_rate_func(self, rxn, model, age, temp, loc, time):
        r = 0
        k = arrhenius_rate_const(model.A[rxn], model.B[rxn], model.E[rxn], model.T[age,temp,time])
        r=k
        for spec in model.component(rxn+"_reactants"):
            if spec in model.gas_set:
                r=r*model.C[spec,age,temp,loc,time]**model.rxn_orders[rxn,spec]
            if self.isSurfSpecSet == True:
                if spec in model.surf_set:
                    r=r*model.q[spec,age,temp,loc,time]**model.rxn_orders[rxn,spec]
                if self.isSitesSet == True:
                    if spec in model.site_set:
                        r=r*model.S[spec,age,temp,loc,time]**model.rxn_orders[rxn,spec]
        return r

    # Define a single equilibrium arrhenius rate function to be used in the model
    #       This function assumes the reaction index (rxn) is valid
    def equilibrium_arrhenius_rate_func(self, rxn, model, age, temp, loc, time):
        r = 0
        (Ar, Er) = equilibrium_arrhenius_consts(model.Af[rxn], model.Ef[rxn], model.dH[rxn], model.dS[rxn])
        kf = arrhenius_rate_const(model.Af[rxn], 0, model.Ef[rxn], model.T[age,temp,time])
        kr = arrhenius_rate_const(Ar, 0, Er, model.T[age,temp,time])
        rf=kf
        rr=kr
        for spec in model.component(rxn+"_reactants"):
            if spec in model.gas_set:
                rf=rf*model.C[spec,age,temp,loc,time]**model.rxn_orders[rxn,spec]
            if self.isSurfSpecSet == True:
                if spec in model.surf_set:
                    rf=rf*model.q[spec,age,temp,loc,time]**model.rxn_orders[rxn,spec]
                if self.isSitesSet == True:
                    if spec in model.site_set:
                        rf=rf*model.S[spec,age,temp,loc,time]**model.rxn_orders[rxn,spec]
        for spec in model.component(rxn+"_products"):
             if spec in model.gas_set:
                 rr=rr*model.C[spec,age,temp,loc,time]**model.rxn_orders[rxn,spec]
             if self.isSurfSpecSet == True:
                 if spec in model.surf_set:
                     rr=rr*model.q[spec,age,temp,loc,time]**model.rxn_orders[rxn,spec]
                 if self.isSitesSet == True:
                     if spec in model.site_set:
                         rr=rr*model.S[spec,age,temp,loc,time]**model.rxn_orders[rxn,spec]
        r = rf-rr
        return r

    # Define a function for the reaction sum for gas species
    def reaction_sum_gas(self, gas_spec, model, age, temp, loc, time):
        r_sum=0
        for r in model.arrhenius_rxns:
            r_sum += model.u_C[gas_spec,r,loc]*self.arrhenius_rate_func(r, model, age, temp, loc, time)
        for re in model.equ_arrhenius_rxns:
            r_sum += model.u_C[gas_spec,re,loc]*self.equilibrium_arrhenius_rate_func(re, model, age, temp, loc, time)
        return r_sum

    # Define a function for the reaction sum for surface species
    def reaction_sum_surf(self, surf_spec, model, age, temp, loc, time):
        r_sum=0
        for r in model.arrhenius_rxns:
            r_sum += model.u_q[surf_spec,r,loc]*self.arrhenius_rate_func(r, model, age, temp, loc, time)
        for re in model.equ_arrhenius_rxns:
            r_sum += model.u_q[surf_spec,re,loc]*self.equilibrium_arrhenius_rate_func(re, model, age, temp, loc, time)
        return r_sum

    # Define a function for the site sum
    def site_sum(self, site_spec, model, age, temp, loc, time):
        sum = 0
        for surf_spec in model.surf_set:
            sum+=model.u_S[site_spec,surf_spec]*model.q[surf_spec,age,temp,loc,time]
        return sum

    # Bulk mass balance constraint
    def bulk_mb_constraint(self, m, gas, age, temp, z, t):
        return m.eb*m.dCb_dt[gas, age, temp, z, t] + m.eb*m.v*m.dCb_dz[gas, age, temp, z, t] == -m.Ga*m.km*(m.Cb[gas, age, temp, z, t] - m.C[gas, age, temp, z, t])

    # Washcoat mass balance constraint
    def pore_mb_constraint(self, m, gas, age, temp, z, t):
        rxn_sum=self.reaction_sum_gas(gas, m, age, temp, z, t)
        return m.ew*(1-m.eb)*m.dC_dt[gas, age, temp, z, t] == m.Ga*m.km*(m.Cb[gas, age, temp, z, t] - m.C[gas, age, temp, z, t]) + (1-m.eb)*rxn_sum

    # Adsorption/surface mass balance constraint
    def surf_mb_constraint(self, m, surf, age, temp, z, t):
        rxn_sum=self.reaction_sum_surf(surf, m, age, temp, z, t)
        return m.dq_dt[surf, age, temp, z, t] == rxn_sum

    # Site density balance constraint
    def site_bal_constraint(self, m, site, age, temp, z, t):
        sum=self.site_sum(site, m, age, temp, z, t)
        return m.Smax[site,age,z,t] - m.S[site, age, temp, z, t] - sum == 0

    # Build Constraints
    def build_constraints(self):
        if self.isRxnBuilt == False:
            print("Error! Cannot build constraints until reaction info is set")
            exit()
        self.model.bulk_cons = Constraint(self.model.gas_set, self.model.age_set,
                                self.model.T_set, self.model.z,
                                self.model.t, rule=self.bulk_mb_constraint)
        self.model.pore_cons = Constraint(self.model.gas_set, self.model.age_set,
                                self.model.T_set, self.model.z,
                                self.model.t, rule=self.pore_mb_constraint)
        if self.isSurfSpecSet == True:
            self.model.surf_cons = Constraint(self.model.surf_set, self.model.age_set,
                                    self.model.T_set, self.model.z,
                                    self.model.t, rule=self.surf_mb_constraint)

            if self.isSitesSet == True:
                self.model.site_cons = Constraint(self.model.site_set, self.model.age_set,
                                        self.model.T_set, self.model.z,
                                        self.model.t, rule=self.site_bal_constraint)
        self.isConBuilt = True

    # Apply a discretizer
    def discretize_model(self, method=DiscretizationMethod.FiniteDifference, elems=20, tstep=100, colpoints=1):
        if self.isConBuilt == False:
            print("Error! Must build the constraints before calling a discretizer")
            exit()

        # Apply the discretizer method
        fd_discretizer = TransformationFactory('dae.finite_difference')
        # Secondary discretizer is for orthogonal collocation methods (if desired)
        oc_discretizer = TransformationFactory('dae.collocation')

        # discretization in time
        fd_discretizer.apply_to(self.model,nfe=tstep,wrt=self.model.t,scheme='BACKWARD')

        if method == DiscretizationMethod.FiniteDifference:
            fd_discretizer.apply_to(self.model,nfe=elems,wrt=self.model.z,scheme='BACKWARD')
        elif method == DiscretizationMethod.OrthogonalCollocation:
            oc_discretizer.apply_to(self.model,nfe=elems,wrt=self.model.z,ncp=colpoints,scheme='LAGRANGE-RADAU')
        else:
            print("Error! Unrecognized discretization method")
            exit()

        # Before exiting, we should initialize some additional parameters that
        #   the discretizer doesn't already handle

        #       Initialize Cb_in
        for spec in self.model.gas_set:
            for age in self.model.age_set:
                for temp in self.model.T_set:
                    val = value(self.model.Cb_in[spec,age,temp,self.model.t.first()])
                    self.model.Cb_in[spec,age,temp, :].set_value(val)

        #       Initialize T
        for age in self.model.age_set:
            for temp in self.model.T_set:
                val = value(self.model.T[age,temp,self.model.t.first()])
                self.model.T[age,temp,:] = val

        #       Initialize age set
        for age in self.model.age_set:
            val = value(self.model.age[age,self.model.t.first()])
            self.model.age[age,:].set_value(val)

        #       Initialize Smax
        if self.isSitesSet == True:
            for site in self.model.site_set:
                for age in self.model.age_set:
                    val = value(self.model.Smax[site,age,self.model.z.first(),self.model.t.first()])
                    self.model.Smax[site,age,:,:].set_value(val)

        #        Initialize u_C
        for spec in self.model.gas_set:
            for rxn in self.model.all_rxns:
                val = value(self.model.u_C[spec,rxn,self.model.z.first()])
                self.model.u_C[spec,rxn,:].set_value(val)

        #        Initialize u_q
        if self.isSurfSpecSet == True:
            for spec in self.model.surf_set:
                for rxn in self.model.all_rxns:
                    val = value(self.model.u_q[spec,rxn,self.model.z.first()])
                    self.model.u_q[spec,rxn,:].set_value(val)

        # For PDE portions, fix the first time derivative at the first node
        for spec in self.model.gas_set:
            for age in self.model.age_set:
                for temp in self.model.T_set:
                    self.model.dCb_dt[spec,age,temp,self.model.z.first(),self.model.t.first()].set_value(0)
                    self.model.dCb_dt[spec,age,temp,self.model.z.first(),self.model.t.first()].fix()

        self.isDiscrete = True

    # Set constant initial conditions
    def set_const_IC(self,spec,age,temp,value):
        if self.isDiscrete == False:
            print("Error! User should call the discretizer before setting initial conditions")
            exit()
        if value < 0:
            print("Error! Concentrations cannot be negative")
            exit()
        if value < 1e-20:
            value = 1e-20
        if spec in self.model.gas_set:
            self.model.Cb[spec,age,temp, :, self.model.t.first()].set_value(value)
            self.model.Cb[spec,age,temp, :, self.model.t.first()].fix()
            self.model.C[spec,age,temp, :, self.model.t.first()].set_value(value)
            self.model.C[spec,age,temp, :, self.model.t.first()].fix()
            self.isInitialSet[spec] = True
        if self.isSurfSpecSet == True:
            if spec in self.model.surf_set:
                self.model.q[spec,age,temp, :, self.model.t.first()].set_value(value)
                self.model.q[spec,age,temp, :, self.model.t.first()].fix()
                self.isInitialSet[spec] = True
            if self.isSitesSet == True:
                if spec in self.model.site_set:
                    # Do not set this initial value (not a time dependent variable)
                    self.isInitialSet[spec] = True

    # Set constant boundary conditions
    def set_const_BC(self,spec,age,temp,value):
        if spec not in self.model.gas_set:
            print("Error! Cannot specify boundary value for non-gas species")
            exit()

        if self.isInitialSet[spec] == False:
            print("Error! User must specify initial conditions before boundary conditions")
            exit()

        if value < 0:
            print("Error! Concentrations cannot be negative")
            exit()
        if value < 1e-20:
            value = 1e-20

        self.model.Cb_in[spec,age,temp, :].set_value(value)
        self.model.Cb[spec,age,temp,self.model.z.first(), :].set_value(value)
        self.model.Cb[spec,age,temp,self.model.z.first(), :].fix()
        self.isBoundarySet[spec] = True

    # Set time dependent BCs using a 'time_value_pairs' list of tuples
    #       If user does not provide an initial value, it will be assumed 1e-20
    def set_time_dependent_BC(self,spec,age,temp,time_value_pairs,initial_value=1e-20):
        if spec not in self.model.gas_set:
            print("Error! Cannot specify boundary value for non-gas species")
            exit()

        if self.isInitialSet[spec] == False:
            print("Error! User must specify initial conditions before boundary conditions")
            exit()

        if type(time_value_pairs) is not list:
            print("Error! Must specify time dependent BCs using a list of tuples: [(t0,value), (t1,value) ...]")
            exit()

        if type(time_value_pairs[0]) is not tuple:
            print("Error! Must specify time dependent BCs using a list of tuples: [(t0,value), (t1,value) ...]")
            exit()

        # Set the first value as given initial_value
        if initial_value < 0:
            print("Error! Concentrations cannot be negative")
            exit()
        if initial_value < 1e-20:
            initial_value = 1e-20
        self.model.Cb_in[spec,age,temp,self.model.t.first()].set_value(initial_value)
        i=0
        current_bc_time = time_value_pairs[i][0]
        current_bc_value = time_value_pairs[i][1]
        for time in self.model.t:
            if time >= current_bc_time:
                try:
                    current_bc_value = time_value_pairs[i][1]
                    if current_bc_value < 0:
                        print("Error! Concentrations cannot be negative")
                        exit()
                    if current_bc_value < 1e-20:
                        current_bc_value = 1e-20
                except:
                    pass
                self.model.Cb_in[spec,age,temp,time].set_value(current_bc_value)
                self.model.Cb[spec,age,temp,self.model.z.first(), time].set_value(current_bc_value)
                self.model.Cb[spec,age,temp,self.model.z.first(), time].fix()
                i+=1
                try:
                    current_bc_time = time_value_pairs[i][0]
                except:
                    pass
            else:
                self.model.Cb_in[spec,age,temp,time].set_value(current_bc_value)
                self.model.Cb[spec,age,temp,self.model.z.first(), time].set_value(current_bc_value)
                self.model.Cb[spec,age,temp,self.model.z.first(), time].fix()

        self.isBoundarySet[spec] = True

    # Function to add linear temperature ramp section
    #       Starting temperature will be whatever the temperature is
    #       at the start time. End temperature will be carried over to
    #       end time (if possible).
    def set_temperature_ramp(self, age, temp, start_time, end_time, end_temp):
        if self.isDiscrete == False:
            print("Error! User should call the discretizer before setting a temperature ramp")
            exit()
        start_temp = value(self.model.T[age,temp,self.model.t.first()])
        previous_time = self.model.t.first()
        for time in self.model.t:
            if time <= start_time:
                start_temp = value(self.model.T[age,temp,self.model.t.first()])
            else:
                if time >= end_time:
                    self.model.T[age,temp,time].set_value(end_temp)
                else:
                    slope = (end_temp-start_temp)/(end_time-start_time)
                    self.model.T[age,temp,time].set_value(start_temp+slope*(time-start_time))
            previous_time = time

    # Function to define reaction 'zones'
    #       By default, all reactions occur in all zones. Users can
    #       utilize this function to specify if a particular reaction
    #       set is only active in a particular 'zone' of the catalyst.
    #       The 'zone' must be specified via a tuple argument where
    #       the first item in the tuple is the start of the zone and
    #       the second argument is the end of the zone. The given
    #       reaction will not occur at points outside the given zone.
    def set_reaction_zone(self, rxn, zone, isNotActive=False):
        if self.isDiscrete == False:
            print("Error! User should call the discretizer before setting a reaction zone")
            exit()
        if rxn not in self.model.all_rxns:
            print("Error! Invalid reaction ID given")
            exit()
        if type(zone) is not tuple:
            print("Error! Zone must be given as tuple: zone=(start_loc, end_loc)")
            exit()
        start_loc = zone[0]
        if start_loc > zone[1]:
            start_loc = zone[1]
            end_loc = zone[0]
        else:
            end_loc = zone[1]
        inside = False
        for loc in self.model.z:
            if loc >= start_loc and loc <= end_loc:
                inside = True
            else:
                inside = False

            if inside == isNotActive:
                for spec in self.model.gas_set:
                    self.model.u_C[spec,rxn,loc].set_value(0)
                if self.isSurfSpecSet == True:
                    for spec in self.model.surf_set:
                        self.model.u_q[spec,rxn,loc].set_value(0)


    # Function to fix all kinetic vars
    def fix_all_reactions(self):
        for r in self.model.arrhenius_rxns:
            self.model.A[r].fix()
            self.model.B[r].fix()
            self.model.E[r].fix()
            self.rxn_list[r]["fixed"]=True
        for re in self.model.equ_arrhenius_rxns:
            self.model.Af[re].fix()
            self.model.Ef[re].fix()
            self.model.dH[re].fix()
            self.model.dS[re].fix()
            self.rxn_list[re]["fixed"]=True

    # Function to fix only a given reaction
    def fix_reaction(self, rxn):
        if rxn in self.model.arrhenius_rxns:
            self.model.A[rxn].fix()
            self.model.B[rxn].fix()
            self.model.E[rxn].fix()
            self.rxn_list[rxn]["fixed"]=True
        if rxn in self.model.equ_arrhenius_rxns:
            self.model.Af[rxn].fix()
            self.model.Ef[rxn].fix()
            self.model.dH[rxn].fix()
            self.model.dS[rxn].fix()
            self.rxn_list[rxn]["fixed"]=True

    # Function to unfix a specified reaction
    def unfix_reaction(self, rxn):
        if rxn in self.model.arrhenius_rxns:
            self.model.A[rxn].unfix()
            self.model.B[rxn].unfix()
            self.model.E[rxn].unfix()
            self.rxn_list[rxn]["fixed"]=False
        if rxn in self.model.equ_arrhenius_rxns:
            self.model.Af[rxn].unfix()
            self.model.Ef[rxn].unfix()
            self.model.dH[rxn].unfix()
            self.model.dS[rxn].unfix()
            self.rxn_list[rxn]["fixed"]=False

    # Function to fix all equilibrium relations
    def fix_all_equilibrium_relations(self):
        for re in self.model.equ_arrhenius_rxns:
            self.model.dH[re].fix()
            self.model.dS[re].fix()
            self.rxn_list[re]["fixed"]=True

    # Function to fix a given equilibrium relation
    def fix_equilibrium_relation(self, rxn):
        if rxn in self.model.equ_arrhenius_rxns:
            self.model.dH[rxn].fix()
            self.model.dS[rxn].fix()
            self.rxn_list[rxn]["fixed"]=True

    # Function to initilize the simulator
    def initialize_simulator(self, console_out=False):
        for spec in self.model.gas_set:
            if self.isBoundarySet[spec] == False:
                print("Error! Must specify boundaries before attempting to solve")
                exit()

        # Setup a dictionary to determine which reaction to unfix after solve
        fixed_dict = {}
        for rxn in self.rxn_list:
            fixed_dict[rxn]=self.rxn_list[rxn]["fixed"]
        self.fix_all_reactions()

        # Run a solve of the model without objective function
        if self.isObjectiveSet == True:
            # TODO: remove obj
            pass

        # Run through model serially solving 1 time step at a time
        '''
            Certain constraints and variables should be deactivated or fixed
            during the initialization solve. For instance, we want to only solve
            at 1 age, 1 temp, and at 1 time for each solve. All other ages, temps,
            and times would be 'fixed' at a given solve.

            Names of Constraints (all active):
            ----------------------------------
                - surf_cons:    (surf_spec, age, temp, loc, time) [optional]
                - site_cons:    (site_spec, age, temp, loc, time) [optional]
                - pore_cons:    (gas_spec,  age, temp, loc, time)
                - bulk_cons:    (gas_spec,  age, temp, loc, time)

                - dq_dt_disc_eq:
                        (surf_spec, age, temp, loc, time)         [optional]
                        {NOTE: 'time' starts after model.t.first()}

                - dCb_dz_disc_eq:
                        (gas_spec,  age, temp, loc, time)
                        {NOTE: Spatial derivatives always active,
                                but should 'turn off' at certain times}

                - dCb_dt_disc_eq:
                        (gas_spec,  age, temp, loc, time)
                        {NOTE: 'time' starts after model.t.first()}

                - dC_dt_disc_eq:
                        (gas_spec,  age, temp, loc, time)
                        {NOTE: 'time' starts after model.t.first()}

            Names of Variables (fixed on initial and boundary):
            ----------------------------------------------------
                NOTE: Variables are already inherently 'fixed' at their initial
                        values (except for S). The 'Cb' varaibles are also
                        inherently 'fixed' at the boundary values.

                - q:    (surf_spec, age, temp, loc, time) [optional]
                - S:    (site_spec, age, temp, loc, time) [optional]
                - C:    (gas_spec,  age, temp, loc, time)
                - Cb:   (gas_spec,  age, temp, loc, time)

                - dq_dt:    (surf_spec, age, temp, loc, time)

                - dCb_dz:   (gas_spec,  age, temp, loc, time)

                - dCb_dt:   (gas_spec,  age, temp, loc, time)
                        {NOTE: ALWAYS 'fixed' at model.z.first() and model.t.first()}

                - dC_dt:    (gas_spec,  age, temp, loc, time)

        '''
        for age_solve in self.model.age_set:
            for temp_solve in self.model.T_set:
                # Fix all ages and temps not currently being solved for
                for age_hold in self.model.age_set:
                    if age_solve != age_hold:
                        # Fix all constraints and vars associated with
                        #   the 'age_hold' id
                        self.model.Cb[:, age_hold, :, :, :].fix()
                        self.model.C[:, age_hold, :, :, :].fix()
                        self.model.dCb_dt[:, age_hold, :, :, :].fix()
                        self.model.dC_dt[:, age_hold, :, :, :].fix()
                        self.model.dCb_dz[:, age_hold, :, :, :].fix()
                        self.model.bulk_cons[:, age_hold, :, :, :].deactivate()
                        self.model.pore_cons[:, age_hold, :, :, :].deactivate()
                        self.model.dCb_dz_disc_eq[:, age_hold, :, :, :].deactivate()
                        self.model.dCb_dt_disc_eq[:, age_hold, :, :, :].deactivate()
                        self.model.dC_dt_disc_eq[:, age_hold, :, :, :].deactivate()

                        if self.isSurfSpecSet == True:
                            self.model.q[:, age_hold, :, :, :].fix()
                            self.model.dq_dt[:, age_hold, :, :, :].fix()
                            self.model.surf_cons[:, age_hold, :, :, :].deactivate()
                            self.model.dq_dt_disc_eq[:, age_hold, :, :, :].deactivate()

                            if self.isSitesSet == True:
                                self.model.S[:, age_hold, :, :, :].fix()
                                self.model.site_cons[:, age_hold, :, :, :].deactivate()

                for temp_hold in self.model.T_set:
                    if temp_solve != temp_hold:
                        # Fix all constraints and vars associated with
                        #   the 'temp_hold' id
                        self.model.Cb[:, :, temp_hold, :, :].fix()
                        self.model.C[:, :, temp_hold, :, :].fix()
                        self.model.dCb_dt[:, :, temp_hold, :, :].fix()
                        self.model.dC_dt[:, :, temp_hold, :, :].fix()
                        self.model.dCb_dz[:, :, temp_hold, :, :].fix()
                        self.model.bulk_cons[:, :, temp_hold, :, :].deactivate()
                        self.model.pore_cons[:, :, temp_hold, :, :].deactivate()
                        self.model.dCb_dz_disc_eq[:, :, temp_hold, :, :].deactivate()
                        self.model.dCb_dt_disc_eq[:, :, temp_hold, :, :].deactivate()
                        self.model.dC_dt_disc_eq[:, :, temp_hold, :, :].deactivate()

                        if self.isSurfSpecSet == True:
                            self.model.q[:, :, temp_hold, :, :].fix()
                            self.model.dq_dt[:, :, temp_hold, :, :].fix()
                            self.model.surf_cons[:, :, temp_hold, :, :].deactivate()
                            self.model.dq_dt_disc_eq[:, :, temp_hold, :, :].deactivate()

                            if self.isSitesSet == True:
                                self.model.S[:, :, temp_hold, :, :].fix()
                                self.model.site_cons[:, :, temp_hold, :, :].deactivate()

                # Inside age_solve && temp_solve
                print("Initializing for " + str(age_solve) + " -> " + str(temp_solve))

                # Fix all times not associated with current time step
                i=0
                for time_solve in self.model.t:
                    if i > 0:
                        for time_hold in self.model.t:
                            if time_solve != time_hold:
                                # Fix all constraints and vars associated with
                                #   the 'time_hold' id
                                self.model.Cb[:, :, :, :, time_hold].fix()
                                self.model.C[:, :, :, :, time_hold].fix()
                                self.model.dCb_dt[:, :, :, :, time_hold].fix()
                                self.model.dC_dt[:, :, :, :, time_hold].fix()
                                self.model.dCb_dz[:, :, :, :, time_hold].fix()
                                self.model.bulk_cons[:, :, :, :, time_hold].deactivate()
                                self.model.pore_cons[:, :, :, :, time_hold].deactivate()
                                self.model.dCb_dz_disc_eq[:, :, :, :, time_hold].deactivate()
                                self.model.dCb_dt_disc_eq[:, :, :, :, time_hold].deactivate()
                                self.model.dC_dt_disc_eq[:, :, :, :, time_hold].deactivate()

                                if self.isSurfSpecSet == True:
                                    self.model.q[:, :, :, :, time_hold].fix()
                                    self.model.dq_dt[:, :, :, :, time_hold].fix()
                                    self.model.surf_cons[:, :, :, :, time_hold].deactivate()
                                    self.model.dq_dt_disc_eq[:, :, :, :, time_hold].deactivate()

                                    if self.isSitesSet == True:
                                        self.model.S[:, :, :, :, time_hold].fix()
                                        self.model.site_cons[:, :, :, :, time_hold].deactivate()

                        #Inside age_solve, temp_solve, and time_solve
                        print("\t...initializing for time =\t" + str(time_solve))
                        solver = SolverFactory('ipopt')
                        results = solver.solve(self.model, tee=console_out)
                        # TODO: Add check for solver fails

                        # Unfix all times (paying close attention to
                        #   specific vars and constraints that should still be
                        #   fixed according to our problem definition)
                        #       (i.e., initial conditions, boundary conditions,
                        #               and dCb_dt at (z=0,t=0) )
                        for time_hold in self.model.t:
                            if time_solve != time_hold:
                                # Fix all constraints and vars associated with
                                #   the 'time_hold' id
                                self.model.Cb[:, age_solve, temp_solve, :, time_hold].unfix()
                                self.model.C[:, age_solve, temp_solve, :, time_hold].unfix()
                                self.model.dCb_dt[:, age_solve, temp_solve, :, time_hold].unfix()
                                self.model.dC_dt[:, age_solve, temp_solve, :, time_hold].unfix()
                                self.model.dCb_dz[:, age_solve, temp_solve, :, time_hold].unfix()
                                self.model.bulk_cons[:, age_solve, temp_solve, :, time_hold].activate()
                                self.model.pore_cons[:, age_solve, temp_solve, :, time_hold].activate()
                                self.model.dCb_dz_disc_eq[:, age_solve, temp_solve, :, time_hold].activate()
                                self.model.dCb_dt_disc_eq[:, age_solve, temp_solve, :, time_hold].activate()
                                self.model.dC_dt_disc_eq[:, age_solve, temp_solve, :, time_hold].activate()

                                if self.isSurfSpecSet == True:
                                    self.model.q[:, age_solve, temp_solve, :, time_hold].unfix()
                                    self.model.dq_dt[:, age_solve, temp_solve, :, time_hold].unfix()
                                    self.model.surf_cons[:, age_solve, temp_solve, :, time_hold].activate()
                                    self.model.dq_dt_disc_eq[:, age_solve, temp_solve, :, time_hold].activate()

                                    if self.isSitesSet == True:
                                        self.model.S[:, age_solve, temp_solve, :, time_hold].unfix()
                                        self.model.site_cons[:, age_solve, temp_solve, :, time_hold].activate()

                            # Make sure the vars that should be fixed, are fixed
                            #   Fix ICs, BCs, and dCb_dt @ z=0, t=0
                            self.model.dCb_dt[:,:,:,self.model.z.first(),self.model.t.first()].fix()
                            self.model.Cb[:,:,:, :, self.model.t.first()].fix()
                            self.model.C[:,:,:, :, self.model.t.first()].fix()
                            if self.isSurfSpecSet == True:
                                self.model.q[:,:,:, :, self.model.t.first()].fix()
                            self.model.Cb[:,:,:,self.model.z.first(), :].fix()
                    else:
                        pass
                    i+=1
                # End time_solve loop


                # Unfix all ages and temps (paying close attention to
                #   specific vars and constraints that should still be
                #   fixed according to our problem definition)
                #       (i.e., initial conditions, boundary conditions,
                #               and dCb_dt at (z=0,t=0) )
                for age_hold in self.model.age_set:
                    if age_solve != age_hold:
                        # UNFix all constraints and vars associated with
                        #   the 'age_hold' id
                        self.model.Cb[:, age_hold, :, :, :].unfix()
                        self.model.C[:, age_hold, :, :, :].unfix()
                        self.model.dCb_dt[:, age_hold, :, :, :].unfix()
                        self.model.dC_dt[:, age_hold, :, :, :].unfix()
                        self.model.dCb_dz[:, age_hold, :, :, :].unfix()
                        self.model.bulk_cons[:, age_hold, :, :, :].activate()
                        self.model.pore_cons[:, age_hold, :, :, :].activate()
                        self.model.dCb_dz_disc_eq[:, age_hold, :, :, :].activate()
                        self.model.dCb_dt_disc_eq[:, age_hold, :, :, :].activate()
                        self.model.dC_dt_disc_eq[:, age_hold, :, :, :].activate()

                        if self.isSurfSpecSet == True:
                            self.model.q[:, age_hold, :, :, :].unfix()
                            self.model.dq_dt[:, age_hold, :, :, :].unfix()
                            self.model.surf_cons[:, age_hold, :, :, :].activate()
                            self.model.dq_dt_disc_eq[:, age_hold, :, :, :].activate()

                            if self.isSitesSet == True:
                                self.model.S[:, age_hold, :, :, :].unfix()
                                self.model.site_cons[:, age_hold, :, :, :].activate()

                for temp_hold in self.model.T_set:
                    if temp_solve != temp_hold:
                        # UNFix all constraints and vars associated with
                        #   the 'temp_hold' id
                        self.model.Cb[:, :, temp_hold, :, :].unfix()
                        self.model.C[:, :, temp_hold, :, :].unfix()
                        self.model.dCb_dt[:, :, temp_hold, :, :].unfix()
                        self.model.dC_dt[:, :, temp_hold, :, :].unfix()
                        self.model.dCb_dz[:, :, temp_hold, :, :].unfix()
                        self.model.bulk_cons[:, :, temp_hold, :, :].activate()
                        self.model.pore_cons[:, :, temp_hold, :, :].activate()
                        self.model.dCb_dz_disc_eq[:, :, temp_hold, :, :].activate()
                        self.model.dCb_dt_disc_eq[:, :, temp_hold, :, :].activate()
                        self.model.dC_dt_disc_eq[:, :, temp_hold, :, :].activate()

                        if self.isSurfSpecSet == True:
                            self.model.q[:, :, temp_hold, :, :].unfix()
                            self.model.dq_dt[:, :, temp_hold, :, :].unfix()
                            self.model.surf_cons[:, :, temp_hold, :, :].activate()
                            self.model.dq_dt_disc_eq[:, :, temp_hold, :, :].activate()

                            if self.isSitesSet == True:
                                self.model.S[:, :, temp_hold, :, :].unfix()
                                self.model.site_cons[:, :, temp_hold, :, :].activate()

                # Make sure the vars that should be fixed, are fixed
                #   Fix ICs, BCs, and dCb_dt @ z=0, t=0
                self.model.dCb_dt[:,:,:,self.model.z.first(),self.model.t.first()].fix()
                self.model.Cb[:,:,:, :, self.model.t.first()].fix()
                self.model.C[:,:,:, :, self.model.t.first()].fix()
                if self.isSurfSpecSet == True:
                    self.model.q[:,:,:, :, self.model.t.first()].fix()
                self.model.Cb[:,:,:,self.model.z.first(), :].fix()


            # End temp_solve loop
        # End age_solve loop


        # Add objective function back
        if self.isObjectiveSet == True:
            # TODO: add obj
            pass

        # After solve, unfix specified reactions
        for rxn in fixed_dict:
            if fixed_dict[rxn] == False:
                self.unfix_reaction(rxn)

        # End Initializer

    # Function to run the solver
    # # TODO: (?) Add additional solver options ?
    def run_solver(self,console_out=True):
        for spec in self.model.gas_set:
            if self.isBoundarySet[spec] == False:
                print("Error! Must specify boundaries before attempting to solve")
                exit()
        if self.isObjectiveSet == False:
            print("Warning! No objective function set. Forcing all kinetics to be fixed.")
            self.fix_all_reactions()

        solver = SolverFactory('ipopt')
        results = solver.solve(self.model, tee=console_out)
        # TODO: Add check for solver fails


    # Function to print out results of variables at all locations and times
    def print_results_all_locations(self, spec_list, age, temp, file_name=""):
        if type(spec_list) is not list:
            print("Error! Need to provide species as a list (even if it is just one species)")
            exit()
        for spec in spec_list:
            if spec not in self.model.all_species_set:
                print("Error! Invalid species given!")
                print("\t"+str(spec)+ " is not a species in the model")
                exit()
        if file_name == "":
            for spec in spec_list:
                file_name+=spec+"_"
            file_name+=str(age)+"_"+str(temp)+"_"
            file_name+="all_loc"
            file_name+=".txt"

        file = open(file_name,"w")

        # Embeddd helper function
        def _print_all_results(model, var, spec, age, temp, file):
            tstart = model.t.first()
            tend = model.t.last()

            #Print header first
            file.write('\t'+'Times (across)'+'\n')
            for time in model.t:
            	if time == tend:
            		file.write(str(time)+'\n')
            	elif time == tstart:
            		file.write('time ->\t'+str(time)+'\t')
            	else:
            		file.write(str(time)+'\t')

            for time in model.t:
            	if time == tend:
            		file.write(str(var)+'[@t='+str(time)+']\n')
            	elif time == tstart:
            		file.write('Z (down)\t'+str(var)+'[@t='+str(time)+']\t')
            	else:
            		file.write(str(var)+'[@t='+str(time)+']\t')

            #Print x results
            for loc in model.z:
            	for time in model.t:
            		if time == tstart:
            			file.write(str(loc)+'\t'+str(value(var[spec,age,temp,loc,time]))+'\t')
            		elif time == tend:
            			file.write(str(value(var[spec,age,temp,loc,time]))+'\n')
            		else:
            			file.write(str(value(var[spec,age,temp,loc,time]))+'\t')
            file.write('\n')

        for spec in spec_list:
            if spec in self.model.gas_set:
                file.write('Results for bulk '+str(spec)+'_b in table below'+'\n')
                _print_all_results(self.model, self.model.Cb, spec, age, temp, file)
                file.write('Results for washcoat '+str(spec)+'_w in table below'+'\n')
                _print_all_results(self.model, self.model.C, spec, age, temp, file)
            elif spec in self.model.surf_set:
                file.write('Results for surface '+str(spec)+' in table below'+'\n')
                _print_all_results(self.model, self.model.q, spec, age, temp, file)
            else:
                file.write('Results for site '+str(spec)+' in table below'+'\n')
                _print_all_results(self.model, self.model.S, spec, age, temp, file)

        file.write('\n')
        file.close()

    # Function to print a list of species at a given node for all times
    def print_results_of_location(self, spec_list, age, temp, loc, file_name=""):
        if type(spec_list) is not list:
            print("Error! Need to provide species as a list (even if it is just one species)")
            exit()
        for spec in spec_list:
            if spec not in self.model.all_species_set:
                print("Error! Invalid species given!")
                print("\t"+str(spec)+ " is not a species in the model")
                exit()
        if file_name == "":
            for spec in spec_list:
                file_name+=spec+"_"
            file_name+=str(age)+"_"+str(temp)+"_"
            file_name+="loc_z_at_"+str(loc)
            file_name+=".txt"

        file = open(file_name,"w")
        file.write('Results for z='+str(loc)+' at in table below'+'\n')
        file.write('Time\t')
        for spec in spec_list:
            if spec in self.model.gas_set:
                file.write(str(spec)+'_b\t'+str(spec)+'_w\t')
            elif spec in self.model.surf_set:
                file.write(str(spec)+'\t')
            else:
                file.write(str(spec)+'\t')
        file.write('\n')
        for time in self.model.t:
            file.write(str(time) + '\t')
            for spec in spec_list:
                if spec in self.model.gas_set:
                    file.write(str(value(self.model.Cb[spec,age,temp,loc,time])) + '\t' + str(value(self.model.C[spec,age,temp,loc,time])) + '\t')
                elif spec in self.model.surf_set:
                    file.write(str(value(self.model.q[spec,age,temp,loc,time])) + '\t')
                else:
                    file.write(str(value(self.model.S[spec,age,temp,loc,time])) + '\t')
            file.write('\n')
        file.write('\n')
        file.close()


    # Function to print a list of species at the exit of the domain
    def print_results_of_breakthrough(self, spec_list, age, temp, file_name=""):
        self.print_results_of_location(spec_list, age, temp, self.model.z.last(), file_name)

    # Print integrated average results over domain for a species
    def print_results_of_integral_average(self, spec_list, age, temp, file_name=""):
        if type(spec_list) is not list:
            print("Error! Need to provide species as a list (even if it is just one species)")
            exit()
        for spec in spec_list:
            if spec not in self.model.all_species_set:
                print("Error! Invalid species given!")
                print("\t"+str(spec)+ " is not a species in the model")
                exit()
        if file_name == "":
            for spec in spec_list:
                file_name+=spec+"_"
            file_name+=str(age)+"_"+str(temp)+"_"
            file_name+="integral_avg"
            file_name+=".txt"

        file = open(file_name,"w")
        file.write('Integral average results in table below'+'\n')
        file.write('Time\t')
        for spec in spec_list:
            if spec in self.model.gas_set:
                file.write(str(spec)+'_b\t'+str(spec)+'_w\t')
            elif spec in self.model.surf_set:
                file.write(str(spec)+'\t')
            else:
                file.write(str(spec)+'\t')
        file.write('\n')
        for time in self.model.t:
            file.write(str(time) + '\t')
            for spec in spec_list:
                if spec in self.model.gas_set:
                    #bulk variable
                    total = 0
                    i = 0
                    for loc in self.model.z:
                        if i == 0:
                            loc_old = loc
                        else:
                            total += (loc - loc_old)*0.5*(value(self.model.Cb[spec,age,temp,loc,time])+value(self.model.Cb[spec,age,temp,loc_old,time]))
                        i += 1
                        loc_old = loc
                    avg = total/(self.model.z.last()-self.model.z.first())
                    file.write(str(avg) + '\t')

                    # Washcoat variable
                    total = 0
                    i = 0
                    for loc in self.model.z:
                        if i == 0:
                            loc_old = loc
                        else:
                            total += (loc - loc_old)*0.5*(value(self.model.C[spec,age,temp,loc,time])+value(self.model.C[spec,age,temp,loc_old,time]))
                        i += 1
                        loc_old = loc
                    avg = total/(self.model.z.last()-self.model.z.first())
                    file.write(str(avg) + '\t')
                elif spec in self.model.surf_set:
                    total = 0
                    i = 0
                    for loc in self.model.z:
                        if i == 0:
                            loc_old = loc
                        else:
                            total += (loc - loc_old)*0.5*(value(self.model.q[spec,age,temp,loc,time])+value(self.model.q[spec,age,temp,loc_old,time]))
                        i += 1
                        loc_old = loc
                    avg = total/(self.model.z.last()-self.model.z.first())
                    file.write(str(avg) + '\t')
                else:
                    total = 0
                    i = 0
                    for loc in self.model.z:
                        if i == 0:
                            loc_old = loc
                        else:
                            total += (loc - loc_old)*0.5*(value(self.model.S[spec,age,temp,loc,time])+value(self.model.S[spec,age,temp,loc_old,time]))
                        i += 1
                        loc_old = loc
                    avg = total/(self.model.z.last()-self.model.z.first())
                    file.write(str(avg) + '\t')
            file.write('\n')
        file.write('\n')
        file.close()


    # # TODO: Add plotting functionality?