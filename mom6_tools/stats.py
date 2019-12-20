#!/usr/bin/env python

"""
Functions used to calculate statistics.
"""

import xarray as xr
import numpy as np
import matplotlib.pyplot as plt
from mom6_tools.DiagsCase import DiagsCase
from mom6_tools.ClimoGenerator import ClimoGenerator
from mom6_tools.m6toolbox import genBasinMasks
from mom6_tools.m6plot import ztplot, plot_stats_da, xyplot
from mom6_tools.MOM6grid import MOM6grid
from datetime import datetime
from collections import OrderedDict
import yaml, os

try: import argparse
except: raise Exception('This version of python is not new enough. python 2.7 or newer is required.')

def options():
  parser = argparse.ArgumentParser(description='''Script for computing and plotting statistics.''')
  parser.add_argument('diag_config_yml_path', type=str, help='''Full path to the yaml file  \
    describing the run and diagnostics to be performed.''')
  parser.add_argument('-diff_rms', help='''Compute horizontal mean difference and RMS: model versus \
                      observations''', action="store_true")
  parser.add_argument('-forcing', help='''Compute global time averages and regionally-averaged time-series \
                      of forcing fields''', action="store_true")
  parser.add_argument('-surface', help='''Compute global time averages and regionally-averaged time-series \
                      of surface fields''', action="store_true")
  parser.add_argument('-debug',   help='''Add priting statements for debugging purposes''', action="store_true")
  parser.add_argument('-savefig', help='''Save figure (.png)''', action="store_true")
  cmdLineArgs = parser.parse_args()
  return cmdLineArgs

def HorizontalMeanRmse_da(var, dims=('yh', 'xh'), weights=None, basins=None, debug=False):
  """
  weighted horizontal root-mean-square error for DataArrays

  Parameters
  ----------

  var : xarray.DataArray
    Difference between the actual values and predicted values (model - obs, or residual).

  dims : tuple, str
    Dimensions over which to apply average. Default is ('yh', 'xh').

  weights : xarray.DataArray, optional
      weights to apply. It can be a masked array.

  basins : xarray.DataArray, optional
      Basins mask to apply. If True, returns horizontal mean RMSE for each basin provided. \
      Basins must be generated by genBasinMasks. Default is False.

  debug : boolean, optional
    If true, print stuff for debugging. Default is False.

  Returns
  -------
  reduced : DataArray or DataSet
      If Basins is provided, returns an DataSet with horizontal mean RMS. Otherwise,
       returns a DataArray.
  """
  check_dims(var,dims)

  if basins is not None and weights is None:
    raise ValueError("Basin masks can only be applied if weights are provided.")

  if weights is None:
    return rms_da(var)
  else:
    if basins is None:
      # global reduction
      if not isinstance(weights, xr.DataArray):
        raise ValueError("weights must be a DataArray")

      check_dims(weights, dims)

      total_weights = weights.sum(dim=dims)
      if debug: print('total weights is:', total_weights.values)
      out = rms_da(var, weights=weights, weights_sum=total_weights)
      if debug: print('rmse is:', out.values)

    else:
      # regional reduction
      if 'region' not in basins.coords:
        raise ValueError("Regions does not have coordinate region. Please use genBasinMasks \
                          to construct the basins mask.")
      if len(weights.shape)!=3:
        raise ValueError("If basins is provided, weights must be a 3D array.")

      if len(basins.shape)!=3:
        raise ValueError("Regions must be a 3D array.")

      rmask_od = OrderedDict()
      for reg in basins.region:
        if debug: print('Region: ', reg)
        # construct a 3D region array
        tmp = np.repeat(basins.sel(region=reg).values[np.newaxis, :, :], len(var.z_l), axis=0)
        region3d = xr.DataArray(tmp,dims=var.dims[1::],
                                coords= {var.dims[1]: var.z_l,
                                         var.dims[2]: var.yh,
                                         var.dims[3]: var.xh})
        if debug: print('region3d:', region3d)
        # select weights to where region3d is one
        tmp_weights = weights.where(region3d == 1.0)
        total_weights = tmp_weights.sum(dim=dims)
        if debug: print('total weights is:', total_weights.values)
        rmask_od[str(reg.values)] = rms_da(var, weights=tmp_weights, weights_sum=total_weights)

        if debug: print('rms is:', rmask_od[str(reg.values)])
      # create DataArray to store output
      out = xr.DataArray(np.zeros((len(basins.region), var.shape[0], var.shape[1])),
                         dims=(basins.dims[0], var.dims[0], var.dims[1]),
                         coords={basins.dims[0]:list(rmask_od.keys()),
                                 var.dims[0]: var.time,
                                 var.dims[1]: var.z_l})
      if debug: print(out)
      for i, rmask_field in enumerate(rmask_od.values()):
        out.values[i,:,:] = rmask_field

    return out

def HorizontalMeanDiff_da(var, dims=('yh', 'xh'), weights=None, basins=None, debug=False):
  """
  weighted horizontal mean difference (model - obs) for DataArrays

  Parameters
  ----------

  var : xarray.DataArray
    Difference between the actual values and predicted values (model - obs, or residual).

  dims : tuple, str
    Dimension(s) over which to apply average. Default is ('yh', 'xh').

  weights : xarray.DataArray
      weights to apply. It can be a masked array.

  basins : xarray.DataArray, optional
      Basins mask to apply. If True, returns horizontal mean difference for each basin provided.
      Basins must be generated by genBasinMasks. Default is False.

  debug : boolean, optional
    If true, print stuff for debugging. Default False

  Returns
  -------
  reduced : DataArray or DataSet
      If Basins is provided, returns an DataSet with horizontal mean difference. Otherwise,
       returns a DataArray.
  """
  check_dims(var,dims)
  if basins is not None and weights is None:
    raise ValueError("Basin masks can only be applied if weights are provided.")

  if weights is None:
    return  var.mean(dim=dims)
  else:
    rmask_od = OrderedDict()
    if basins is None:
      # global reduction
      if not isinstance(weights, xr.DataArray):
        raise ValueError("weights must be a DataArray")
      check_dims(weights,dims)
      total_weights = weights.sum(dim=dims)
      if debug: print('total weights is:', total_weights.values)
      out = mean_da(var, weights=weights, weights_sum=total_weights)
      if debug: print('horizontal mean is:', out)
    else:
      # regional reduction
      if 'region' not in basins.coords:
        raise ValueError("Regions does not have coordinate region. Please use genBasinMasks \
                          to construct the basins mask.")
      if len(weights.shape)!=3:
        raise ValueError("If basins is provided, weights must be a 3D array.")

      if len(basins.shape)!=3:
        raise ValueError("Regions must be a 3D array.")

      for reg in basins.region:
        if debug: print('Region: ', reg)
        # construct a 3D region array
        tmp = np.repeat(basins.sel(region=reg).values[np.newaxis, :, :], len(var.z_l), axis=0)
        region3d = xr.DataArray(tmp,dims=var.dims[1::],
                                coords= {var.dims[1]: var.z_l,
                                         var.dims[2]: var.yh,
                                         var.dims[3]: var.xh})
        if debug: print('region3d:', region3d)
        # select weights to where region3d is one
        tmp_weights = weights.where(region3d == 1.0)
        total_weights = tmp_weights.sum(dim=dims)
        rmask_od[str(reg.values)] = mean_da(var, weights=tmp_weights, weights_sum=total_weights)
        if debug: print('horizontal mean is:', rmask_od[str(reg.values)])
      # create dataArray to store rmask_od
      out = xr.DataArray(np.zeros((len(basins.region), var.shape[0], var.shape[1])),
                         dims=(basins.dims[0], var.dims[0], var.dims[1]),
                         coords={basins.dims[0]:list(rmask_od.keys()),
                                 var.dims[0]: var.time,
                                 var.dims[1]: var.z_l})

    for i, rmask_field in enumerate(rmask_od.values()):
      out.values[i,:,:] = rmask_field

    return out

def min_da(da, dims=('yh', 'xh')):
  """
  Calculates the minimun value in DataArray da,

  ----------
  da : xarray.DataArray
        DataArray for which to compute the min.

  dims : tuple, str
    Dimension(s) over which to apply reduction. Default is ('yh', 'xh').

  Returns
  -------
  reduction : DataSet
      xarray.Dataset with min for da.
  """
  check_dims(da,dims)
  return da.min(dim=dims, keep_attrs=True)

def max_da(da, dims=('yh', 'xh')):
  """
  Calculates the maximum value in DataArray da.

  ----------
  da : xarray.DataArray
        DataArray for which to compute the max.

  dims : tuple, str
    Dimension(s) over which to apply reduction. Default is ('yh', 'xh').

  Returns
  -------
  reduction : DataSet
      xarray.Dataset with the max for da.
  """
  check_dims(da,dims)
  return da.max(dim=dims, keep_attrs=True)

def mean_da(da, dims=('yh', 'xh'), weights=None,  weights_sum=None):
  """
  Calculates the mean value in DataArray da (optional weighted mean).

  ----------
  da : xarray.DataArray
        DataArray for which to compute (weighted) mean.

  dims : tuple, str
    Dimension(s) over which to apply reduction. Default is ('yh', 'xh').

  weights : xarray.DataArray, optional
    weights to apply. It can be a masked array.

  weights_sum : xarray.DataArray, optional
    Total weight (i.e., weights.sum()). Only computed if not provided.

  Returns
  -------
  reduction : DataSet
      xarray.Dataset with (optionally weighted) mean for da.
  """
  check_dims(da,dims)
  if weights is not None:
    if weights_sum is None: weights_sum = weights.sum(dim=dims)
    out = ((da * weights).sum(dim=dims) / weights_sum)
    # copy attrs
    out.attrs = da.attrs
    return out
  else:
    return da.mean(dim=dims, keep_attrs=True)

def std_da(da, dims=('yh', 'xh'), weights=None,  weights_sum=None, da_mean=None):
  """
  Calculates the std in DataArray da (optional weighted std).

  ----------
  da : xarray.DataArray
        DataArray for which to compute (weighted) std.

  dims : tuple, str
    Dimension(s) over which to apply reduction. Default is ('yh', 'xh').

  weights : xarray.DataArray, optional
    weights to apply. It can be a masked array.

  weights_sum : xarray.DataArray, optional
    Total weight (i.e., weights.sum()). Only computed if not provided.

  da_mean : xarray.DataArray, optional
   Mean value in DataArray da. Only computed if not provided.

  Returns
  -------
  reduction : DataSet
      xarray.Dataset with (optionally weighted) std for da.
  """

  check_dims(da,dims)
  if weights is not None:
    if weights_sum is None:
      weights_sum = weights.sum(dim=dims)
    if da_mean is None: da_mean = mean_da(da, dims, weights, weights_sum)
    out = np.sqrt(((da-da_mean)**2 * weights).sum(dim=dims)/weights_sum)
    # copy attrs
    out.attrs = da.attrs
    return out
  else:
    return da.std(dim=dims, keep_attrs=True)

def rms_da(da, dims=('yh', 'xh'), weights=None,  weights_sum=None):
  """
  Calculates the rms in DataArray da (optional weighted rms).

  ----------
  da : xarray.DataArray
        DataArray for which to compute (weighted) rms.

  dims : tuple, str
    Dimension(s) over which to apply reduction. Default is ('yh', 'xh').

  weights : xarray.DataArray, optional
    weights to apply. It can be a masked array.

  weights_sum : xarray.DataArray, optional
    Total weight (i.e., weights.sum()). Only computed if not provided.

  Returns
  -------
  reduction : DataSet
      xarray.Dataset with (optionally weighted) rms for da.
  """

  check_dims(da,dims)
  if weights is not None:
    if weights_sum is None: weights_sum = weights.sum(dim=dims)
    out = np.sqrt((da**2 * weights).sum(dim=dims)/weights_sum)
    # copy attrs
    out.attrs = da.attrs
    return out
  else:
    return np.sqrt((da**2).mean(dim=dims, keep_attrs=True))

def check_dims(da,dims):
  """
  Checks if dims exists in ds.
  ----------
  da : xarray.DataArray
        DataArray for which to compute (weighted) min.

  dims : tuple, str
    Dimension(s) over which to apply reduction.
  """
  if dims[0] not in da.dims:
    raise ValueError("DataArray does not have dimensions given by dims[0]")
  if dims[1] not in da.dims:
    raise ValueError("DataArray does not have dimensions given by dims[1]")

  return

def myStats_da(da, weights, dims=('yh', 'xh'), basins=None, debug=False):
  """
  Calculates min, max, mean, standard deviation and root-mean-square for DataArray da
  and returns Dataset with values.

  Parameters
  ----------
  da : xarray.DataArray
        DataArray for which to compute weighted stats.

  dims : tuple, str
    Dimension(s) over which to apply reduction. Default is ('yh', 'xh').

  weights : xarray.DataArray
    weights to apply. It can be a masked array.

  basins : xarray.DataArray, optional
    Basins mask to apply. If True, returns horizontal mean RMSE for each basin provided. \
    Basins must be generated by genBasinMasks. Default is False.

  debug : boolean, optional
    If true, print stuff for debugging. Default is False.

  Returns
  -------
  reduced : DataSet
      New xarray.Dataset with min, max and weighted mean, standard deviation and
      root-mean-square for DataArray ds.
  """
  check_dims(da,dims)
  if weights is None:
    print('compute weights here')
    # compute weights here...

  rmask_od = OrderedDict()
  if basins is None:
    # global
    total_weights = weights.sum(dim=dims)
    da_min  = min_da(da, dims)
    da_max  = max_da(da, dims)
    da_mean = mean_da(da, dims, weights,  total_weights)
    da_std  = std_da(da, dims, weights,  total_weights, da_mean)
    da_rms  = rms_da(da, dims, weights,  total_weights)

    if debug: print_stats(da_min, da_max, da_mean, da_std, da_rms)

    out = stats_to_ds(da_min, da_max, da_mean, da_std, da_rms)
    # copy attrs
    out.attrs = da.attrs
    rmask_od['Global'] = out

  else:
    # aplpy reduction for each basin
    if 'region' not in basins.coords:
      raise ValueError("Regions does not have coordinate region. Please use genBasinMasks \
                        to construct the basins mask.")
    for reg in basins.region:
      if debug: print('Region: ', reg)
      # select region in the DataArray
      da_reg = da.where(basins.sel(region=reg).values == 1.0)
      # select weights to where region values are one
      tmp_weights = weights.where(basins.sel(region=reg).values == 1.0)
      total_weights = tmp_weights.sum(dim=dims)
      da_min  = min_da(da_reg , dims)
      da_max  = max_da(da_reg , dims)
      da_mean = mean_da(da_reg, dims, tmp_weights,  total_weights)
      da_std  = std_da(da_reg , dims, tmp_weights,  total_weights, da_mean)
      da_rms  = rms_da(da_reg , dims, tmp_weights,  total_weights)

      if debug:
        print_stats(da_min, da_max, da_mean, da_std, da_rms)

      out = stats_to_ds(da_min, da_max, da_mean, da_std, da_rms)
      rmask_od[str(reg.values)] = out

  return dict_to_da(rmask_od) # create dataarray using rmask_od

def print_stats(da_min, da_max, da_mean, da_std, da_rms):
  """
  Print values for debugging purposes.

  Parameters
  ----------

  da_* : xarray.DataArray
    DataArrays with min, max, std, mean, rms.
  """
  print('myStats: min(da) =' ,da_min)
  print('myStats: max(da) =' ,da_max)
  print('myStats: mean(da) =',da_mean)
  print('myStats: std(da) =' ,da_std)
  print('myStats: rms(da) =' ,da_rms)
  return

def stats_to_ds(da_min, da_max, da_mean, da_std, da_rms):
  """
  Creates a xarray.Dataset using DataArrays provided.

  Parameters
  ----------

  da_* : xarray.DataArray
    DataArrays with min, max, std, mean, rms.

  Returns
  -------
  ds : DataSet
      xarray.Dataset with min, max, mean, standard deviation and
      root-mean-square.
  """
  var = np.zeros(len(da_min.time))
  # create dataset with zeros
  ds = xr.Dataset(data_vars={ 'da_min' : (('time'), var),
                              'da_max' : (('time'), var),
                              'da_std' : (('time'), var),
                              'da_rms' : (('time'), var),
                              'da_mean': (('time'), var)},
                   coords={'time': da_mean['time']})
  # fill dataset with correct values
  ds['da_mean'] = da_mean; ds['da_std'] = da_std; ds['da_rms'] = da_rms
  ds['da_min'] = da_min; ds['da_max'] = da_max
  return ds

def dict_to_da(stats_dict):
  """
  Creates a xarray.DataArray using keys in dictionary (stats_dict).

  Parameters
  ----------

  stats_dict : OrderedDict
    Dictionary with statistics computed using function myStats_da

  Returns
  -------
  da : DataSet
      DataArray with min, max, mean, standard deviation and
      root-mean-square for different basins.
  """

  time = stats_dict[list(stats_dict.items())[0][0]].time
  basins = list(stats_dict.keys())
  stats = ['da_min', 'da_max', 'da_mean', 'da_std', 'da_rms']
  var = np.zeros((len(basins),len(stats),len(time)))
  da = xr.DataArray(var, dims=['basin', 'stats', 'time'],
                           coords={'basin': basins,
                                   'stats': stats,
                                   'time': time},)
  for reg in (basins):
    da.sel(basin=reg).sel(stats='da_min').values[:] = stats_dict[reg].da_min.values
    da.sel(basin=reg).sel(stats='da_max').values[:] = stats_dict[reg].da_max.values
    da.sel(basin=reg).sel(stats='da_mean').values[:]= stats_dict[reg].da_mean.values
    da.sel(basin=reg).sel(stats='da_std').values[:] = stats_dict[reg].da_std.values
    da.sel(basin=reg).sel(stats='da_rms').values[:] = stats_dict[reg].da_rms.values

  return da

def main(stream=False):

  # Get options
  args = options()

  # Read in the yaml file
  diag_config_yml = yaml.load(open(args.diag_config_yml_path,'r'), Loader=yaml.Loader)

  # Create the case instance
  dcase = DiagsCase(diag_config_yml['Case'], xrformat=True)
  print('Casename is:', dcase.casename)
  RUNDIR = dcase.get_value('RUNDIR')

  # read grid
  grd = MOM6grid(RUNDIR+'/'+dcase.casename+'.mom6.static.nc', xrformat=True)
  area = grd.Ah.where(grd.wet > 0)

  # Get masking for different regions
  depth = grd.depth_ocean.values
  # remove Nan's, otherwise genBasinMasks won't work
  depth[np.isnan(depth)] = 0.0
  basin_code = genBasinMasks(grd.geolon.values, grd.geolat.values, depth, xda=True)

  #select a few basins, namely, Global, PersianGulf, Arctic, Pacific, Atlantic, Indian, Southern, LabSea and BaffinBay
  basins = basin_code.isel(region=[0,1,7,8,9,10,11,12,13])

  if not args.diff_rms and not args.surface and not args.forcing:
    raise ValueError("Please select -diff_rms, -surface and/or -forcing.")

  if args.diff_rms:
    horizontal_mean_diff_rms(grd, dcase, basins, args)

  if args.surface:
    variables = ['SSH','tos','sos','mlotst','oml']
    fname = '.mom6.sfc_*.nc'
    xystats(grd, dcase, basins, args)

  if args.forcing:
    variables = ['friver','ficeberg','fsitherm','hfsnthermds','sfdsi', 'hflso',
             'seaice_melt_heat', 'wfo', 'hfds', 'Heat_PmE']
    fname = '.mom6.hm_*.nc'
    xystats(grd, dcase, basins, args)

  return


def xystats(fname, variables, grd, dcase, basins, args):
  '''
   Compute and plot statistics for 2D variables.

   Parameters
  ----------

  fname : str
    Name of the file to be processed.

  variables : str
    List of variables to be processed.

  grd : OrderedDict
    Dictionary with statistics computed using function myStats_da

  dcase : case object
    Object created using mom6_tools.DiagsCase.

  basins : DataArray
   Basins mask to apply. Returns horizontal mean RMSE for each basin provided.
   Basins must be generated by genBasinMasks.

  args : object
    Object with command line options.

  Returns
  -------
    Plots min, max, mean, std and rms for variables provided and for different basins.

  '''
  try:
    from ncar_jobqueue import NCARCluster
    from dask.distributed import Client
    parallel = True
  except:
    parallel = False

  RUNDIR = dcase.get_value('RUNDIR')
  area = grd.Ah.where(grd.wet > 0)
  if args.debug: print('RUNDIR:', RUNDIR)

  # initiate NCAR cluster
  cluster = NCARCluster(project='P93300612')
  cluster.scale(2)

  client = Client(cluster)

  # read forcing files
  if args.debug: startTime = datetime.now()
  if parallel:
    ds = xr.open_mfdataset(RUNDIR+'/'+dcase.casename+'.mom6.hm_*.nc', data_vars=variables, \
                               chunks={'time': 12}, parallel=True)
  else:
    ds = xr.open_mfdataset(RUNDIR+'/'+dcase.casename+'.mom6.hm_*.nc', data_vars=variables)
  if args.debug: print('\nTime elasped: ', datetime.now() - startTime)

  for var in variables:
    if args.savefig:
      savefig1=str(var)+'_xymean.png'
      savefig2=str(var)+'_stats.png'
    else:
      savefig1=None
      savefig2=None

    # yearly mean
    ds_yr = ds[var].resample(time="1Y", closed='left', keep_attrs=True).mean(dim='time', keep_attrs=True).load()
    stats = myStats_da(ds_yr, weights=area, basins=basins)
    plot_stats_da(stats, var, ds[var].attrs['units'], save=savefig2)
    dummy = np.ma.masked_invalid(ds_yr.mean(dim='time').values)
    xyplot(dummy, grd.geolon.values, grd.geolat.values, area.values, save=savefig1,
           suptitle=ds[var].attrs['long_name'] +' ['+ ds[var].attrs['units']+']',
           title='Averaged between ' +str(ds_yr.time[0].values) + ' and '+ str(ds_yr.time[-1].values))

  # close processes
  if args.debug: print('Close dask workers...\n')
  client.close(); cluster.close()

  return

def horizontal_mean_diff_rms(grd, dcase, basins, args):
  '''
   Compute horizontal mean difference and rms: model versus observations.

   Parameters
  ----------

  grd : OrderedDict
    Dictionary with statistics computed using function myStats_da

  dcase : case object
    Object created using mom6_tools.DiagsCase.

  basins : DataArray
   Basins mask to apply. Returns horizontal mean RMSE for each basin provided.
   Basins must be generated by genBasinMasks.

  args : object
    Object with command line options.

  Returns
  -------
    Plots horizontal mean difference and rms for different basins.

  '''

  RUNDIR = dcase.get_value('RUNDIR')
  area = grd.Ah.where(grd.wet > 0)
  if args.debug: print('RUNDIR:', RUNDIR)

  # initiate NCAR cluster
  cluster = NCARCluster(project='P93300612')
  cluster.scale(2)

  client = Client(cluster)
  print(cluster.dashboard_link)

  # read dataset
  if args.debug: startTime = datetime.now()
  # since we are loading 3D data, chunksize in time = 1
  ds = xr.open_mfdataset(RUNDIR+'/'+dcase.casename+'.mom6.h_*.nc', chunks={'time': 1}, \
                         parallel=True)
  if args.debug:
    print('Read dataset', ds)
    print('\nTime elasped: ', datetime.now() - startTime)

  # Compute climatologies
  thetao_model = ds.thetao.resample(time="1Y", closed='left', keep_attrs=True).mean(dim='time', \
                                    keep_attrs=True).persist()

  salt_model = ds.so.resample(time="1Y", closed='left', keep_attrs=True).mean(dim='time', \
                               keep_attrs=True).persist()

  # load PHC2 data
  phc_path = '/glade/p/cesm/omwg/obs_data/phc/'
  phc_temp = xr.open_mfdataset(phc_path+'PHC2_TEMP_tx0.66v1_34lev_ann_avg.nc', decode_times=False)
  phc_salt = xr.open_mfdataset(phc_path+'PHC2_SALT_tx0.66v1_34lev_ann_avg.nc', decode_times=False)

  # get theta and salt and rename coordinates to be the same as the model's
  thetao_obs = phc_temp.TEMP.rename({'X': 'xh','Y': 'yh', 'depth': 'z_l'});
  salt_obs = phc_salt.SALT.rename({'X': 'xh','Y': 'yh', 'depth': 'z_l'});
  # set coordinates to the same as the model's
  thetao_obs['xh'] = thetao_model.xh; thetao_obs['yh'] = thetao_model.yh;
  salt_obs['xh'] = salt_model.xh; salt_obs['yh'] = salt_model.yh;

  # compute difference
  temp_diff = thetao_model - thetao_obs
  salt_diff = salt_model - salt_obs

  # construct a 3D area with land values masked
  area3d = np.repeat(area.values[np.newaxis, :, :], len(temp_diff.z_l), axis=0)
  mask3d = xr.DataArray(area3d, dims=(temp_diff.dims[1:4]), coords= {temp_diff.dims[1]: temp_diff.z_l,
                                                                   temp_diff.dims[2]: temp_diff.yh,
                                                                   temp_diff.dims[3]: temp_diff.xh})
  area3d_masked = mask3d.where(temp_diff[0,:] == temp_diff[0,:])

  # Horizontal Mean difference (model - obs)
  if args.debug: print('Computing Horizontal Mean difference for temperature...\n')
  if args.debug: startTime = datetime.now()
  temp_bias = HorizontalMeanDiff_da(temp_diff,weights=area3d_masked, basins=basins)
  if args.debug: print('\nTime elasped: ', datetime.now() - startTime)
  if args.debug: print('Computing Horizontal Mean difference for salt...\n')
  if args.debug: startTime = datetime.now()
  salt_bias = HorizontalMeanDiff_da(salt_diff,weights=area3d_masked, basins=basins)
  if args.debug: print('\nTime elasped: ', datetime.now() - startTime)

  # Horizontal Mean rms (model - obs)
  if args.debug: print('Computing Horizontal Mean rms for temperature...\n')
  if args.debug: startTime = datetime.now()
  temp_rms = HorizontalMeanRmse_da(temp_diff,weights=area3d_masked, basins=basins)
  if args.debug: print('\nTime elasped: ', datetime.now() - startTime)
  if args.debug: print('Computing Horizontal Mean rms for salt...\n')
  salt_rms = HorizontalMeanRmse_da(salt_diff,weights=area3d_masked, basins=basins)
  if args.debug: print('\nTime elasped: ', datetime.now() - startTime)

  # close processes
  if args.debug: print('Close workers...\n')
  client.close(); cluster.close()

  # temperature
  for reg in temp_bias.region:
    if args.debug: print('Temperature bias for region:', str(reg.values))
    # remove Nan's
    diff_reg = temp_bias.sel(region=reg).dropna('z_l')
    if diff_reg.z_l.max() <= 500.0:
      splitscale = None
    else:
      splitscale =  [0., -500., -diff_reg.z_l.max()]
    if args.savefig:
      savefig_diff=str(reg.values)+'temp_diff.png'
      savefig_rms=str(reg.values)+'temp_rms.png'
    else:
      savefig_diff=None
      savefig_rms=None

    ztplot(diff_reg.values, diff_reg.time.values, diff_reg.z_l.values*-1, ignore=np.nan, splitscale=splitscale,
           suptitle=dcase._casename, contour=True, title= str(reg.values) + ', Potential Temperature [C], diff (model - obs)',
           extend='both', colormap='dunnePM', autocenter=True, tunits='Year', show=True,
           save=savefig_diff, interactive=True);

    ztplot(diff_reg.values, diff_reg.time.values, diff_reg.z_l.values*-1, ignore=np.nan, splitscale=splitscale,
           suptitle=dcase._casename, contour=True, title= str(reg.values) + ', Potential Temperature [C], rms (model - obs)',
           extend='both', colormap='dunnePM', autocenter=False, tunits='Year', show=True,
           save=savefig_rms, interactive=True);

  # salinity
  for reg in salt_bias.region:
    if args.debug: print('Salinity bias for region:', str(reg.values))
    # remove Nan's
    diff_reg = salt_bias.sel(region=reg).dropna('z_l')
    if diff_reg.z_l.max() <= 500.0:
      splitscale = None
    else:
      splitscale =  [0., -500., -diff_reg.z_l.max()]

    if args.savefig:
      savefig_diff=str(reg.values)+'salt_diff.png'
      savefig_rms=str(reg.values)+'salt_rms.png'
    else:
      savefig_diff=None
      savefig_rms=None

    ztplot(diff_reg.values, diff_reg.time.values, diff_reg.z_l.values*-1, ignore=np.nan, splitscale=splitscale,
           suptitle=dcase._casename, contour=True, title= str(reg.values) + ', Salinity [psu], diff (model - obs)',
           extend='both', colormap='dunnePM', autocenter=True, tunits='Year', show=True,
           save=savefig_diff, interactive=True);

    ztplot(diff_reg.values, diff_reg.time.values, diff_reg.z_l.values*-1, ignore=np.nan, splitscale=splitscale,
           suptitle=dcase._casename, contour=True, title= str(reg.values) + ', Salinity [psu], rms (model - obs)',
           extend='both', colormap='dunnePM', autocenter=False, tunits='Year', show=True,
           save=savefig_rms, interactive=True);
  return

if __name__ == '__main__':
  main()
