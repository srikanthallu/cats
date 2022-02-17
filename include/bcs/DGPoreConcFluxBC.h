/*!
 *  \file DGPoreConcFluxBC.h
 *	\brief Boundary Condition kernel for the flux of concentration/density across a boundary of the domain
 *	\details This file creates a generic boundary condition kernel for the flux of matter accross
 *			a boundary. The flux is based on a velocity vector, as well as domain porosity, and is valid
 *			in all directions and all boundaries of a DG method. Since the DG method's flux boundary
 *			conditions are essitially the same for input and ouput boundaries, this kernel will check
 *			the sign of the flux normal to the boundary and determine automattically whether it is
 *			an output or input boundary, then apply the appropriate conditions.
 *
 *      Reference: B. Riviere, Discontinous Galerkin methods for solving elliptic and parabolic equations:
 *                    Theory and Implementation, SIAM, Houston, TX, 2008.
 *
 *
 *  \author Austin Ladshaw
 *	\date 03/09/2020
 *	\copyright This kernel was designed and built at Oak Ridge National
 *              Laboratory by Austin Ladshaw for research in catalyst
 *              performance for new vehicle technologies.
 *
 *			   Austin Ladshaw does not claim any ownership or copyright to the
 *			   MOOSE framework in which these kernels are constructed, only
 *			   the kernels themselves. The MOOSE framework copyright is held
 *			   by the Battelle Energy Alliance, LLC (c) 2010, all rights reserved.
 */

#pragma once

#include "DGConcentrationFluxBC.h"

/// DGPoreConcFluxBC class object inherits from DGConcentrationFluxBC object
/** This class object inherits from the DGConcentrationFluxBC object.
	All public and protected members of this class are required function overrides.
	The flux BC uses the velocity in the system to apply a boundary
	condition based on whether or not material is leaving or entering the boundary. */
class DGPoreConcFluxBC : public DGConcentrationFluxBC
{
public:
  /// Required new syntax for InputParameters
  static InputParameters validParams();

	/// Required constructor for BC objects in MOOSE
	DGPoreConcFluxBC(const InputParameters & parameters);

protected:
	/// Required function override for BC objects in MOOSE
	/** This function returns a residual contribution for this object.*/
	virtual Real computeQpResidual() override;

	/// Required function override for BC objects in MOOSE
	/** This function returns a Jacobian contribution for this object. The Jacobian being
		computed is the associated diagonal element in the overall Jacobian matrix for the
		system and is used in preconditioning of the linear sub-problem. */
	virtual Real computeQpJacobian() override;

	/// Not Required, but aids in the preconditioning step
	/** This function returns the off diagonal Jacobian contribution for this object. By
		returning a non-zero value we will hopefully improve the convergence rate for the
		cross coupling of the variables. */
	virtual Real computeQpOffDiagJacobian(unsigned int jvar) override;

  const VariableValue & _porosity;			    ///< Porosity variable
  const unsigned int _porosity_var;					///< Variable identification for porosity

private:

};
