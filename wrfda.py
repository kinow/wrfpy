#!/usr/bin/env python

'''
description:    WRFDA part of wrfpy
license:        APACHE 2.0
author:         Ronald van Haren, NLeSC (r.vanharen@esciencecenter.nl)
'''

import os
import f90nml
import subprocess
import shutil
import utils
from config import config
from datetime import datetime
import time

class wrfda(config):
  '''
  description
  '''
  def __init__(self):
    config.__init__(self)  # load config
    self.rundir = self.config['filesystem']['wrf_run_dir']
    self.wrfda_workdir = os.path.join(self.config['filesystem']['work_dir'],
                                      'wrfda')
   
  def run(self, datestart):
    '''
    Run all WRFDA steps
    '''
    self.obsproc_init(datestart)
    #self.obsproc_run()
    self.prepare_updatebc(datestart)  # prepares for updating low bc
    self.updatebc_run()  # run da_updatebc.exe
    import pdb; pdb.set_trace()
    self.prepare_wrfda()  # prepare for running da_wrfvar.exe
    self.wrfvar_run()  # run da_wrfvar.exe
    self.prepare_updatebc_type('lateral', datestart, 1)  # prepare for updating lateral bc
    self.updatebc_run()  # run da_updatebc.exe
    self.wrfda_post()  # copy files over to WRF run_dir

  def obsproc_init(self, datestart):
    '''
    Sync obsproc namelist with WRF namelist.input
    '''
    from shutil import copyfile
    from datetime import timedelta
    from datetime import datetime
    # copy default 3dvar obsproc namelist to namelist.obsproc
    obsproc_dir = os.path.join(self.config['filesystem']['wrfda_dir'],
                               'var/obsproc')
    # read obsproc namelist
    obsproc_nml = f90nml.read(os.path.join(obsproc_dir,
                                           'namelist.obsproc.3dvar.wrfvar-tut'))
    # read WRF namelist in WRF work_dir
    wrf_nml = f90nml.read(os.path.join(self.config['filesystem']['wrf_run_dir'],
                                       'namelist.input'))
    # copy observation in LITTLE_R format to obsproc_dir
    shutil.copyfile(os.path.join(
      self.config['filesystem']['obs_dir'],
      self.config['filesystem']['obs_filename']), os.path.join(
        obsproc_dir, self.config['filesystem']['obs_filename']))
    # sync obsproc namelist variables with wrf namelist.input
    obsproc_nml['record1']['obs_gts_filename'] = str(self.config[
      'filesystem']['obs_filename'])  # convert unicode str to regular str
    obsproc_nml['record8']['nesti'] = wrf_nml['domains']['i_parent_start']
    obsproc_nml['record8']['nestj'] = wrf_nml['domains']['j_parent_start']
    obsproc_nml['record8']['nestix'] = wrf_nml['domains']['e_we']
    obsproc_nml['record8']['nestjx'] = wrf_nml['domains']['e_sn']
    obsproc_nml['record8']['numc'] = wrf_nml['domains']['parent_id']
    obsproc_nml['record8']['dis'] = wrf_nml['domains']['dx']
    obsproc_nml['record8']['maxnes'] = wrf_nml['domains']['max_dom']
    # set time_analysis, time_window_min, time_window_max
    # check if both datestart and dateend are a datetime instance
    if not isinstance(datestart, datetime):
      raise TypeError("datestart must be an instance of datetime")
    obsproc_nml['record2']['time_analysis'] = datetime.strftime(datestart,
                                                        '%Y-%m-%d_%H:%M:%S')
    obsproc_nml['record2']['time_window_min'] = datetime.strftime(
      datestart - timedelta(minutes=15), '%Y-%m-%d_%H:%M:%S')
    obsproc_nml['record2']['time_window_max'] = datetime.strftime(
      datestart + timedelta(minutes=15), '%Y-%m-%d_%H:%M:%S')
    # save obsproc_nml
    utils.silentremove(os.path.join(obsproc_dir, 'namelist.obsproc'))
    obsproc_nml.write(os.path.join(obsproc_dir, 'namelist.obsproc'))


  def obsproc_run(self):
    '''
    run obsproc.exe
    '''
    obsproc_dir = os.path.join(self.config['filesystem']['wrfda_dir'],
                               'var/obsproc')
    # TODO: check if output is file is created and no errors have occurred
    j_id = None
    if len(self.config['options_slurm']['slurm_obsproc.exe']):
      # run using slurm
      if j_id:
        mid = "--dependency=afterok:%d" %j_id
        obsproc_command = ['sbatch', mid, self.config['options_slurm']['slurm_obsproc.exe']]
      else:
        obsproc_command = ['sbatch', self.config['options_slurm']['slurm_obsproc.exe']]
      utils.check_file_exists(obsproc_command[-1])
      try:
        res = subprocess.check_output(obsproc_command, cwd=obsproc_dir,
                                      stderr=utils.devnull())
        j_id = int(res.split()[-1])  # slurm job-id
      except subprocess.CalledProcessError:
        logger.error('Obsproc failed %s:' %obsproc_command)
        raise  # re-raise exception
      return j_id  # return slurm job-id
    else:
      # run locally
      subprocess.check_call(os.path.join(obsproc_dir, 'obsproc.exe'), cwd=obsproc_dir,
                            stdout=utils.devnull(), stderr=utils.devnull())

      return None


  def prepare_symlink_files(self, domain):
    '''
    prepare WRFDA directory
    '''
    obsproc_dir = os.path.join(self.config['filesystem']['wrfda_dir'],
                               'var/obsproc')
    # define domain specific workdir
    workdir = os.path.join(self.wrfda_workdir, "d0" + str(domain))
    # symlink da_wrfvar.exe, LANDUSE.TBL, be.dat.cv3
    os.symlink(os.path.join(
      self.config['filesystem']['wrfda_dir'],'var/da/da_wrfvar.exe'
      ), os.path.join(wrfda_workdir, 'da_wrfvar.exe'))
    os.symlink(os.path.join(
      self.config['filesystem']['wrfda_dir'],'var/run/be.dat.cv3'
      ), os.path.join(wrfda_workdir, 'be.dat'))
    os.symlink(os.path.join(
      self.config['filesystem']['wrfda_dir'],'run/LANDUSE.TBL'
      ), os.path.join(wrfda_workdir, 'LANDUSE.TBL'))
    # symlink output of obsproc
    os.symlink(os.path.join(self.config['filesystem']['wrfda_dir'],
               'var/obsproc/obs_gts_' + obsproc_nml['record2']['time_analysis'] + '.3DVAR',
              ), os.path.join(wrfda_workdir, 'ob.ascii'))


  def create_parame(self, parame_type, domain):
    # set domain specific workdir
    wrfda_workdir = os.path.join(self.wrfda_workdir, "d0" + str(domain))
    filename = os.path.join(wrfda_workdir, 'parame.in')
    utils.silentremove(filename)
    # add configuration to parame.in file
    parame = open(filename, 'w')  # open file
    if parame_type == 'lower':
      ## start config file lower boundary conditions
      parame.write("""&control_param
        da_file = './fg'
        wrf_input = './wrfinput_d01'
        wrf_input = '/home/WUR/haren009/sources/WRFV3/run/wrfinput_d01'
        domain_id = 1
        cycling = .true.
        debug = .true.
        low_bdy_only = .true.
        update_lsm = .false.
        var4d_lbc = .false.
        iswater = 16
    /
    """)
      ## end config file lower boundary conditions
    else:
      ## start config file lateral boundary conditions
      parame.write("""&control_param
        da_file = '/home/haren/model/WRFV3/run2/wrfinput_d01'
        wrf_bdy_file = './wrfbdy_d01'
        domain_id = 1
        cycling = .true.
        debug = .true.
        update_low_bdy = .false.
        update_lateral_bdy = .true.
        update_lsm = .false.
        var4d_lbc = .false.
    /
    """)
      ## end config file lateral boundary conditions
    parame.close()  # close file


  def prepare_wrfda_namelist(self, domain):
    # set domain specific workdir
    wrfda_workdir = os.path.join(self.wrfda_workdir, "d0" + str(domain))
    # read WRFDA namelist
    wrfda_namelist = os.path.join(self.config['filesystem']['wrfda_dir'],
                                  'var/test/tutorial/namelist.input')
    wrfda_nml = f90nml.read(wrfda_namelist)

    # read WRF namelist in WRF work_dir
    wrf_nml = f90nml.read(os.path.join(self.config['filesystem']['wrf_run_dir'],
                                       'namelist.input'))
    ## silent remove file if exists
    ##utils.silentremove(os.path.join(wrfda_workdir, 'fg'))
    ## create symlink of wrfinput_d0${domain}
    ##os.symlink(os.path.join(self.rundir, 'wrfinput_d0' + str(domain)),
    ##          os.path.join(wrfda_workdir, 'fg'))
    # set domain specific information in namelist
    for var in ['e_we', 'e_sn', 'e_vert', 'dx', 'dy']:
      # get variable from ${RUNDIR}/namelist.input
      var_value = wrf_nml['domains'][var]
      # set domain specific variable in WRDFA_WORKDIR/namelist.input
      wrfda_nml['domains'][var] = var_value[domain - 1]
    for var in ['mp_physics', 'ra_lw_physics', 'ra_sw_physics', 'radt',
                'sf_sfclay_physics', 'sf_surface_physics', 'bl_pbl_physics',
                'cu_physics', 'cudt', 'num_soil_layers']:
      # get variable from ${RUNDIR}/namelist.input
      var_value = wrf_nml['physics'][var]
      # set domain specific variable in WRDFA_WORKDIR/namelist.input
      try:
        wrfda_nml['physics'][var] = var_value[domain - 1]
      except TypeError:
        wrfda_nml['physics'][var] = var_value
    obsproc_dir = os.path.join(self.config['filesystem']['wrfda_dir'],
                               'var/obsproc')
    obsproc_nml = f90nml.read(os.path.join(obsproc_dir, 'namelist.obsproc'))
    # sync wrfda namelist with obsproc namelist
    wrfda_nml['wrfvar18']['analysis_date'] = obsproc_nml['record2']['time_analysis']
    wrfda_nml['wrfvar21']['time_window_min'] = obsproc_nml['record2']['time_window_min']
    wrfda_nml['wrfvar22']['time_window_max'] = obsproc_nml['record2']['time_window_max']
    wrfda_nml['wrfvar7']['cv_options'] =  3
    tana = utils.return_validate(obsproc_nml['record2']['time_analysis'][:-6])
    wrfda_nml['time_control']['start_year'] = tana.year 
    wrfda_nml['time_control']['start_month'] = tana.month   
    wrfda_nml['time_control']['start_day'] = tana.day
    wrfda_nml['time_control']['start_hour'] = tana.hour   
    wrfda_nml['time_control']['end_year'] = tana.year  
    wrfda_nml['time_control']['end_month'] = tana.month
    wrfda_nml['time_control']['end_day'] = tana.day
    wrfda_nml['time_control']['end_hour'] = tana.hour
    # save changes to wrfda_nml
    utils.silentremove(os.path.join(wrfda_workdir, 'namelist.input'))
    wrfda_nml.write(os.path.join(wrfda_workdir, 'namelist.input'))

 
  def prepare_wrfda(self):
    '''
    prepare WRFDA
    '''
    # read WRF namelist in WRF work_dir
    wrf_nml = f90nml.read(os.path.join(self.config['filesystem']['wrf_run_dir'],
                                       'namelist.input'))
    # maximum domain number
    max_dom = wrf_nml['domains']['max_dom']
    # prepare a WRFDA workdirectory for each domain
    for domain in range(1, max_dom+1):
      self.prepare_symlink_files(domain)
      self.prepare_wrfda_namelist(domain)


  def wrfvar_run(self):
    '''
    run da_wrfvar.exe
    '''
    logfile = os.path.join(self.wrfda_workdir, 'log.wrfda_d' + str(domain))
    j_id = None
    if len(self.config['options_slurm']['slurm_wrfvar.exe']):
      if j_id:
        mid = "--dependency=afterok:%d" %j_id
        wrfvar_command = ['sbatch', mid, self.config['options_slurm']['slurm_wrfvar.exe']]
      else:
        wrfvar_command = ['sbatch', self.config['options_slurm']['slurm_wrfvar.exe']]
    utils.check_file_exists(wrfvar_command[-1])
    try:
      res = subprocess.check_output(wrfvar_command, cwd=self.wrfda_workdir,
                                    stderr=utils.devnull())
      j_id = int(res.split()[-1])  # slurm job-id
    except subprocess.CalledProcessError:
      logger.error('Wrfvar failed %s:' %wrfvar_command)
      raise  # re-raise exception
    while True:
      time.sleep(1)
      if not utils.testjob(j_id):
        break
    else:
      # run locally
      subprocess.check_call([os.path.join(self.wrfda_workdir, 'da_wrfvar.exe'), '>&!', logfile],
                            cwd=self.wrfda_workdir, stdout=utils.devnull(), stderr=utils.devnull())


  def prepare_updatebc(self, datestart):
    # read WRF namelist in WRF work_dir
    wrf_nml = f90nml.read(os.path.join(self.config['filesystem']['wrf_run_dir'],
                                       'namelist.input'))
    # maximum domain number
    max_dom = wrf_nml['domains']['max_dom']
    # prepare a WRFDA workdirectory for each domain
    for domain in range(1, max_dom+1):
      # TODO: add check for domain is int
      # define domain specific workdir
      wrfda_workdir = os.path.join(self.wrfda_workdir, "d0" + str(domain))
      # general functionality independent of boundary type in parame.in
      if os.path.exists(wrfda_workdir):
        shutil.rmtree(wrfda_workdir)  # remove wrfda_workdir
      utils._create_directory(os.path.join(wrfda_workdir, 'var', 'da'))
      wrf_nml = f90nml.read(os.path.join(self.config['filesystem']['wrf_run_dir'],
                                         'namelist.input'))
      # define parame.in file
      self.create_parame('lower', domain)
      # symlink da_update_bc.exe
      os.symlink(os.path.join(
        self.config['filesystem']['wrfda_dir'],'var/da/da_update_bc.exe'
        ), os.path.join(wrfda_workdir, 'da_update_bc.exe'))
      # copy wrfbdy_d01 file (lateral boundaries) to WRFDA_WORKDIR
      shutil.copyfile(os.path.join(self.rundir, 'wrfbdy_d01'),
                      os.path.join(wrfda_workdir, 'wrfbdy_d01'))
      # set parame.in file for updating lower boundary first
      self.prepare_updatebc_type('lower', datestart, domain)


  def prepare_updatebc_type(self, boundary_type, datestart, domain):
    # set domain specific workdir
    wrfda_workdir = os.path.join(self.wrfda_workdir, "d0" + str(domain))
    if boundary_type == 'lower' :
      # copy first guess (wrfout in wrfinput format) for WRFDA
      first_guess = os.path.join(self.rundir, 'wrfvar_input_d0' + str(domain) +
                                '_' + datetime.strftime(datestart,
                                                        '%Y-%m-%d_%H:%M:%S'))
      try:
        shutil.copyfile(first_guess, os.path.join(wrfda_workdir, 'fg'))
      except Exception:
        shutil.copyfile(os.path.join(self.rundir, 'wrfinput_d0' + str(domain)),
                        os.path.join(wrfda_workdir, 'fg'))
      # read parame.in file
      parame = f90nml.read(os.path.join(wrfda_workdir, 'parame.in'))
      # set domain in parame.in
      parame['control_param']['domain_id'] = domain
      # set wrf_input (IC from WPS and WRF real)
      parame['control_param']['wrf_input'] = str(os.path.join(
        self.rundir, 'wrfinput_d0' + str(domain)))
      # save changes to parame.in file
      utils.silentremove(os.path.join(wrfda_workdir, 'parame.in'))
      parame.write(os.path.join(wrfda_workdir, 'parame.in'))
    elif boundary_type == 'lateral' :
      # read parame.in file
      parame = f90nml.read(os.path.join(wrfda_workdir, 'parame.in'))
      # set output from WRFDA
      parame['control_param']['da_file'] = os.path.join(wrfda_workdir, 'wrfvar_output')
      # save changes to parame.in file
      utils.silentremove(os.path.join(wrfda_workdir, 'parame.in'))
      parame.write(os.path.join(wrfda_workdir, 'parame.in'))
    else:
      raise Exception('unknown boundary type')


  def updatebc_run(self):
    # run da_update_bc.exe
    j_id = None
    if len(self.config['options_slurm']['slurm_updatebc.exe']):
      if j_id:
        mid = "--dependency=afterok:%d" %j_id
        updatebc_command = ['sbatch', mid, self.config['options_slurm']['slurm_updatebc.exe']]
      else:
        updatebc_command = ['sbatch', self.config['options_slurm']['slurm_updatebc.exe']]
      try:
        res = subprocess.check_output(updatebc_command, cwd=self.wrfda_workdir,
                                      stderr=utils.devnull())
        j_id = int(res.split()[-1])  # slurm job-id
      except subprocess.CalledProcessError:
        logger.error('Updatebc failed %s:' %updatebc_command)
        raise  # re-raise exception
    while True:
      time.sleep(0.5)
      if not utils.testjob(j_id):
        break
    else:
      # run locally
      subprocess.check_call(os.path.join(self.wrfda_workdir, 'da_update_bc.exe'),
                            cwd=self.wrfda_workdir,
                            stdout=utils.devnull(), stderr=utils.devnull())

  def wrfda_post(self):
    '''
    Move files into WRF run dir after all data assimilation steps have completed
    '''
    # read WRF namelist in WRF work_dir
    wrf_nml = f90nml.read(os.path.join(self.config['filesystem']['wrf_run_dir'],
                                       'namelist.input'))
    # maximum domain number
    max_dom = wrf_nml['domains']['max_dom']
    # prepare a WRFDA workdirectory for each domain
    for domain in range(1, max_dom+1):
      # set domain specific workdir
      wrfda_workdir = os.path.join(self.wrfda_workdir, "d0" + str(domain))
      # copy updated first guess to RUNDIR/wrfinput
      utils.silentremove(os.path.join(self.rundir, 'wrfinput_d0' + str(domain)))
      shutil.move(os.path.join(wrfda_workdir, 'fg'),
                  os.path.join(self.rundir, 'wrfinput_d0' + str(domain)))
      if domain==1:
        # copy over updated lateral boundary conditions to RUNDIR
        # only for outer domain
        utils.silentremove(os.path.join(self.rundir, 'wrfbdy_d01'))
        shutil.copyfile(os.path.join(wrfda_workdir, 'wrfbdy_d01'),
                      os.path.join(self.rundir, 'wrfbdy_d01'))
      # copy wrfvar_output_d0${domain} to ${RUNDIR}/wrfinput_d0${domain}
      utils.silentremove(os.path.join(self.rundir ,'wrfinput_d0' + str(domain)))
      shutil.copyfile(os.path.join(wrfda_workdir, 'wrfvar_output'),
                      os.path.join(self.rundir, 'wrfinput_d0' + str(domain)))


 
if __name__ == "__main__":
  datestart= datetime(2014,07,27,02)
  wrf_da = wrfda()
  wrf_da.run(datestart)
