# Copyright (C) 2013  Ian Harry
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 3 of the License, or (at your
# option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General
# Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

#
# =============================================================================
#
#                                   Preamble
#
# =============================================================================
#

"""
This library code contains functions and classes that are used to set up
and add jobs/nodes to a pycbc workflow. For details about pycbc.workflow see:
https://ldas-jobs.ligo.caltech.edu/~cbc/docs/pycbc/ahope.html
"""

import math, os
import lal
from ligo import segments
from pycbc.workflow.core import Executable, File, FileList, Node

def int_gps_time_to_str(t):
    """Takes an integer GPS time, either given as int or lal.LIGOTimeGPS, and
    converts it to a string. If a LIGOTimeGPS with nonzero decimal part is
    given, raises a ValueError."""
    int_t = int(t)
    if abs(float(t - int_t)) > 0.:
        raise ValueError('Need an integer GPS time, got %s' % str(t))
    return str(int_t)

def select_tmpltbank_class(curr_exe):
    """ This function returns a class that is appropriate for setting up
    template bank jobs within workflow.

    Parameters
    ----------
    curr_exe : string
        The name of the executable to be used for generating template banks.

    Returns
    --------
    exe_class : Sub-class of pycbc.workflow.core.Executable that holds utility
        functions appropriate for the given executable.  Instances of the class
        ('jobs') **must** have methods
        * job.create_node()
        and
        * job.get_valid_times(ifo, )
    """
    exe_to_class_map = {
        'pycbc_geom_nonspinbank'  : PyCBCTmpltbankExecutable,
        'pycbc_aligned_stoch_bank': PyCBCTmpltbankExecutable
    }
    try:
        return exe_to_class_map[curr_exe]
    except KeyError:
        raise NotImplementedError(
            "No job class exists for executable %s, exiting" % curr_exe)

def select_matchedfilter_class(curr_exe):
    """ This function returns a class that is appropriate for setting up
    matched-filtering jobs within workflow.

    Parameters
    ----------
    curr_exe : string
        The name of the matched filter executable to be used.

    Returns
    --------
    exe_class : Sub-class of pycbc.workflow.core.Executable that holds utility
        functions appropriate for the given executable.  Instances of the class
        ('jobs') **must** have methods
        * job.create_node()
        and
        * job.get_valid_times(ifo, )
    """
    exe_to_class_map = {
        'pycbc_inspiral'          : PyCBCInspiralExecutable,
        'pycbc_inspiral_skymax'   : PyCBCInspiralExecutable,
        'pycbc_multi_inspiral'    : PyCBCMultiInspiralExecutable,
    }
    try:
        return exe_to_class_map[curr_exe]
    except KeyError:
        # also conceivable to introduce a default class??
        raise NotImplementedError(
            "No job class exists for executable %s, exiting" % curr_exe)

def select_generic_executable(workflow, exe_tag):
    """ Returns a class that is appropriate for setting up jobs to run executables
    having specific tags in the workflow config.
    Executables should not be "specialized" jobs fitting into one of the
    select_XXX_class functions above, i.e. not a matched filter or template
    bank job, which require extra setup.

    Parameters
    ----------
    workflow : pycbc.workflow.core.Workflow
        The Workflow instance.

    exe_tag : string
        The name of the config section storing options for this executable and
        the option giving the executable path in the [executables] section.

    Returns
    --------
    exe_class : Sub-class of pycbc.workflow.core.Executable that holds utility
        functions appropriate for the given executable.  Instances of the class
        ('jobs') **must** have a method job.create_node()
    """
    exe_path = workflow.cp.get("executables", exe_tag)
    exe_name = os.path.basename(exe_path)
    exe_to_class_map = {
        'ligolw_add'               : LigolwAddExecutable,
        'lalapps_inspinj'          : LalappsInspinjExecutable,
        'pycbc_create_injections'  : PycbcCreateInjectionsExecutable,
        'pycbc_condition_strain'         : PycbcConditionStrainExecutable
    }
    try:
        return exe_to_class_map[exe_name]
    except KeyError:
        # Should we try some sort of default class??
        raise NotImplementedError(
            "No job class exists for executable %s, exiting" % exe_name)

def sngl_ifo_job_setup(workflow, ifo, out_files, curr_exe_job, science_segs,
                       datafind_outs, parents=None,
                       allow_overlap=True):
    """ This function sets up a set of single ifo jobs. A basic overview of how this
    works is as follows:

    * (1) Identify the length of data that each job needs to read in, and what
      part of that data the job is valid for.
    * START LOOPING OVER SCIENCE SEGMENTS
    * (2) Identify how many jobs are needed (if any) to cover the given science
      segment and the time shift between jobs. If no jobs continue.
    * START LOOPING OVER JOBS
    * (3) Identify the time that the given job should produce valid output (ie.
      inspiral triggers) over.
    * (4) Identify the data range that the job will need to read in to produce
      the aforementioned valid output.
    * (5) Identify all parents/inputs of the job.
    * (6) Add the job to the workflow
    * END LOOPING OVER JOBS
    * END LOOPING OVER SCIENCE SEGMENTS

    Parameters
    -----------
    workflow: pycbc.workflow.core.Workflow
        An instance of the Workflow class that manages the constructed workflow.
    ifo : string
        The name of the ifo to set up the jobs for
    out_files : pycbc.workflow.core.FileList
        The FileList containing the list of jobs. Jobs will be appended
        to this list, and it does not need to be empty when supplied.
    curr_exe_job : Job
        An instanced of the Job class that has a get_valid times method.
    science_segs : ligo.segments.segmentlist
        The list of times that the jobs should cover
    datafind_outs : pycbc.workflow.core.FileList
        The file list containing the datafind files.
    parents : pycbc.workflow.core.FileList (optional, kwarg, default=None)
        The FileList containing the list of jobs that are parents to
        the one being set up.
    allow_overlap : boolean (optional, kwarg, default = True)
        If this is set the times that jobs are valid for will be allowed to
        overlap. This may be desired for template banks which may have some
        overlap in the times they cover. This may not be desired for inspiral
        jobs, where you probably want triggers recorded by jobs to not overlap
        at all.

    Returns
    --------
    out_files : pycbc.workflow.core.FileList
        A list of the files that will be generated by this step in the
        workflow.
    """

    ########### (1) ############
    # Get the times that can be analysed and needed data lengths
    data_length, valid_chunk, valid_length = identify_needed_data(curr_exe_job)

    exe_tags = curr_exe_job.tags
    # Loop over science segments and set up jobs
    for curr_seg in science_segs:
        ########### (2) ############
        # Initialize the class that identifies how many jobs are needed and the
        # shift between them.
        segmenter = JobSegmenter(data_length, valid_chunk, valid_length,
                                 curr_seg, curr_exe_job)

        for job_num in range(segmenter.num_jobs):
            ############## (3) #############
            # Figure out over what times this job will be valid for
            job_valid_seg = segmenter.get_valid_times_for_job(job_num,
                                                   allow_overlap=allow_overlap)

            ############## (4) #############
            # Get the data that this job should read in
            job_data_seg = segmenter.get_data_times_for_job(job_num)

            ############# (5) ############
            # Identify parents/inputs to the job
            if parents:
                # Find the set of files with the best overlap
                curr_parent = parents.find_outputs_in_range(ifo, job_valid_seg,
                                                            useSplitLists=True)
                if not curr_parent:
                    err_string = ("No parent jobs found overlapping %d to %d."
                                  %(job_valid_seg[0], job_valid_seg[1]))
                    err_string += "\nThis is a bad error! Contact a developer."
                    raise ValueError(err_string)
            else:
                curr_parent = [None]

            curr_dfouts = None
            if datafind_outs:
                curr_dfouts = datafind_outs.find_all_output_in_range(ifo,
                                              job_data_seg, useSplitLists=True)
                if not curr_dfouts:
                    err_str = ("No datafind jobs found overlapping %d to %d."
                                %(job_data_seg[0],job_data_seg[1]))
                    err_str += "\nThis shouldn't happen. Contact a developer."
                    raise ValueError(err_str)


            ############## (6) #############
            # Make node and add to workflow

            # Note if I have more than one curr_parent I need to make more than
            # one job. If there are no curr_parents it is set to [None] and I
            # make a single job. This catches the case of a split template bank
            # where I run a number of jobs to cover a single range of time.

            for parent in curr_parent:
                if len(curr_parent) != 1:
                    bank_tag = [t for t in parent.tags if 'bank' in t.lower()]
                    curr_exe_job.update_current_tags(bank_tag + exe_tags)
                # We should generate unique names automatically, but it is a
                # pain until we can set the output names for all Executables
                node = curr_exe_job.create_node(job_data_seg, job_valid_seg,
                                                parent=parent,
                                                df_parents=curr_dfouts)
                workflow.add_node(node)
                curr_out_files = node.output_files
                # FIXME: Here we remove PSD files if they are coming through.
                #        This should be done in a better way. On to-do list.
                curr_out_files = [i for i in curr_out_files if 'PSD_FILE'\
                                                                 not in i.tags]
                out_files += curr_out_files

    return out_files

def multi_ifo_coherent_job_setup(workflow, out_files, curr_exe_job,
                                 science_segs, datafind_outs, output_dir,
                                 parents=None, slide_dict=None, tags=None):
    """
    Method for setting up coherent inspiral jobs.
    """
    if tags is None:
        tags = []
    data_seg, job_valid_seg = curr_exe_job.get_valid_times()
    curr_out_files = FileList([])
    if 'IPN' in datafind_outs[-1].description \
            and 'bank_veto_bank' in datafind_outs[-2].description:
        # FIXME: This looks like a really nasty hack for the GRB code.
        #        This should be fixed properly to avoid strange behaviour!
        ipn_sky_points = datafind_outs[-1]
        bank_veto = datafind_outs[-2]
        frame_files = datafind_outs[:-2]
    else:
        ipn_sky_points = None
        if 'bank_veto_bank' in datafind_outs[-1].name:
            bank_veto = datafind_outs[-1]
            frame_files = datafind_outs[:-1]
        else:
            bank_veto = None
            frame_files = datafind_outs

    split_bank_counter = 0

    if curr_exe_job.injection_file is None:
        for split_bank in parents:
            tag = list(tags)
            tag.append(split_bank.tag_str)
            node = curr_exe_job.create_node(data_seg, job_valid_seg,
                    parent=split_bank, dfParents=frame_files,
                    bankVetoBank=bank_veto, ipn_file=ipn_sky_points,
                    slide=slide_dict, tags=tag)
            workflow.add_node(node)
            split_bank_counter += 1
            curr_out_files.extend(node.output_files)
    else:
        for inj_file in curr_exe_job.injection_file:
            for split_bank in parents:
                tag = list(tags)
                tag.append(inj_file.tag_str)
                tag.append(split_bank.tag_str)
                node = curr_exe_job.create_node(data_seg, job_valid_seg,
                        parent=split_bank, inj_file=inj_file, tags=tag,
                        dfParents=frame_files, bankVetoBank=bank_veto,
                        ipn_file=ipn_sky_points)
                workflow.add_node(node)
                split_bank_counter += 1
                curr_out_files.extend(node.output_files)

    # FIXME: Here we remove PSD files if they are coming
    #        through. This should be done in a better way. On
    #        to-do list.
    # IWHNOTE: This will not be needed when coh_PTF is retired, but it is
    #          okay to do this. It just means you can't access these files
    #          later.
    curr_out_files = [i for i in curr_out_files if 'PSD_FILE'\
                      not in i.tags]
    out_files += curr_out_files

    return out_files

def identify_needed_data(curr_exe_job):
    """ This function will identify the length of data that a specific
    executable needs to analyse and what part of that data is valid (ie.
    inspiral doesn't analyse the first or last 8s of data it reads in).

    Parameters
    -----------
    curr_exe_job : Job
        An instance of the Job class that has a get_valid times method.

    Returns
    --------
    dataLength : float
        The amount of data (in seconds) that each instance of the job must read
        in.
    valid_chunk : ligo.segments.segment
        The times within dataLength for which that jobs output **can** be
        valid (ie. for inspiral this is (72, dataLength-72) as, for a standard
        setup the inspiral job cannot look for triggers in the first 72 or
        last 72 seconds of data read in.)
    valid_length : float
        The maximum length of data each job can be valid for. This is
        abs(valid_segment).
    """
    # Set up the condorJob class for the current executable
    data_lengths, valid_chunks = curr_exe_job.get_valid_times()

    # Begin by getting analysis start and end, and start and end of time
    # that the output file is valid for
    valid_lengths = [abs(valid_chunk) for valid_chunk in valid_chunks]

    return data_lengths, valid_chunks, valid_lengths


class JobSegmenter(object):
    """ This class is used when running sngl_ifo_job_setup to determine what times
    should be analysed be each job and what data is needed.
    """

    def __init__(self, data_lengths, valid_chunks, valid_lengths, curr_seg,
                 curr_exe_class):
        """ Initialize class. """
        self.exe_class = curr_exe_class
        self.curr_seg = curr_seg
        self.curr_seg_length = float(abs(curr_seg))

        self.data_length, self.valid_chunk, self.valid_length = \
                      self.pick_tile_size(self.curr_seg_length, data_lengths,
                                                  valid_chunks, valid_lengths)

        self.data_chunk = segments.segment([0, self.data_length])
        self.data_loss = self.data_length - abs(self.valid_chunk)

        if self.data_loss < 0:
            raise ValueError("pycbc.workflow.jobsetup needs fixing! Please contact a developer")

        if self.curr_seg_length < self.data_length:
            self.num_jobs = 0
            return

        # How many jobs do we need
        self.num_jobs = int( math.ceil( (self.curr_seg_length \
                                - self.data_loss) / float(self.valid_length) ))

        if self.curr_seg_length == self.data_length:
            # If the segment length is identical to the data length then I
            # will have exactly 1 job!
            self.job_time_shift = 0
        else:
            # What is the incremental shift between jobs
            self.job_time_shift = (self.curr_seg_length - self.data_length) / \
                                   float(self.num_jobs - 1)

    def pick_tile_size(self, seg_size, data_lengths, valid_chunks, valid_lengths):
        """ Choose job tiles size based on science segment length """

        if len(valid_lengths) == 1:
            return data_lengths[0], valid_chunks[0], valid_lengths[0]
        else:
            # Pick the tile size that is closest to 1/3 of the science segment
            target_size = seg_size / 3
            pick, pick_diff = 0, abs(valid_lengths[0] - target_size)
            for i, size in enumerate(valid_lengths):
                if abs(size - target_size) < pick_diff:
                    pick, pick_diff  = i, abs(size - target_size)
            return data_lengths[pick], valid_chunks[pick], valid_lengths[pick]

    def get_valid_times_for_job(self, num_job, allow_overlap=True):
        """ Get the times for which this job is valid. """
        # small factor of 0.0001 to avoid float round offs causing us to
        # miss a second at end of segments.
        shift_dur = self.curr_seg[0] + int(self.job_time_shift * num_job\
                                           + 0.0001)
        job_valid_seg = self.valid_chunk.shift(shift_dur)
        # If we need to recalculate the valid times to avoid overlap
        if not allow_overlap:
            data_per_job = (self.curr_seg_length - self.data_loss) / \
                           float(self.num_jobs)
            lower_boundary = num_job*data_per_job + \
                                 self.valid_chunk[0] + self.curr_seg[0]
            upper_boundary = data_per_job + lower_boundary
            # NOTE: Convert to int after calculating both boundaries
            # small factor of 0.0001 to avoid float round offs causing us to
            # miss a second at end of segments.
            lower_boundary = int(lower_boundary)
            upper_boundary = int(upper_boundary + 0.0001)
            if lower_boundary < job_valid_seg[0] or \
                    upper_boundary > job_valid_seg[1]:
                err_msg = ("Workflow is attempting to generate output "
                          "from a job at times where it is not valid.")
                raise ValueError(err_msg)
            job_valid_seg = segments.segment([lower_boundary,
                                              upper_boundary])
        return job_valid_seg

    def get_data_times_for_job(self, num_job):
        """ Get the data that this job will read in. """
        # small factor of 0.0001 to avoid float round offs causing us to
        # miss a second at end of segments.
        shift_dur = self.curr_seg[0] + int(self.job_time_shift * num_job\
                                           + 0.0001)
        job_data_seg = self.data_chunk.shift(shift_dur)
        # Sanity check that all data is used
        if num_job == 0:
            if job_data_seg[0] != self.curr_seg[0]:
                err= "Job is not using data from the start of the "
                err += "science segment. It should be using all data."
                raise ValueError(err)
        if num_job == (self.num_jobs - 1):
            if job_data_seg[1] != self.curr_seg[1]:
                err = "Job is not using data from the end of the "
                err += "science segment. It should be using all data."
                raise ValueError(err)

        if hasattr(self.exe_class, 'zero_pad_data_extend'):
            job_data_seg = self.exe_class.zero_pad_data_extend(job_data_seg,
                                                                 self.curr_seg)

        return job_data_seg


class PyCBCInspiralExecutable(Executable):
    """ The class used to create jobs for pycbc_inspiral Executable. """

    current_retention_level = Executable.ALL_TRIGGERS
    time_dependent_options = ['--channel-name']

    def __init__(self, cp, exe_name, ifo=None, out_dir=None,
                 injection_file=None, tags=None, reuse_executable=False):
        if tags is None:
            tags = []
        super().__init__(cp, exe_name, ifo, out_dir, tags=tags,
                         reuse_executable=reuse_executable,
                         set_submit_subdir=False)
        self.cp = cp
        self.injection_file = injection_file
        self.ext = '.hdf'

        self.num_threads = 1
        if self.get_opt('processing-scheme') is not None:
            stxt = self.get_opt('processing-scheme')
            if len(stxt.split(':')) > 1:
                self.num_threads = stxt.split(':')[1]

    def create_node(self, data_seg, valid_seg, parent=None, df_parents=None,
                    tags=None):
        if tags is None:
            tags = []
        node = Node(self, valid_seg=valid_seg)
        if not self.has_opt('pad-data'):
            raise ValueError("The option pad-data is a required option of "
                             "%s. Please check the ini file." % self.name)
        pad_data = int(self.get_opt('pad-data'))

        # set remaining options flags
        node.add_opt('--gps-start-time',
                     int_gps_time_to_str(data_seg[0] + pad_data))
        node.add_opt('--gps-end-time',
                     int_gps_time_to_str(data_seg[1] - pad_data))
        node.add_opt('--trig-start-time', int_gps_time_to_str(valid_seg[0]))
        node.add_opt('--trig-end-time', int_gps_time_to_str(valid_seg[1]))

        if self.injection_file is not None:
            node.add_input_opt('--injection-file', self.injection_file)

        # set the input and output files
        fil = node.new_output_file_opt(
            valid_seg,
            self.ext,
            '--output',
            tags=tags,
            store_file=self.retain_files,
            use_tmp_subdirs=True
        )

        # For inspiral jobs we overrwrite the "relative.submit.dir"
        # attribute to avoid too many files in one sub-directory
        curr_rel_dir = fil.name.split('/')[0]
        node.add_profile('pegasus', 'relative.submit.dir',
                         self.pegasus_name + '_' + curr_rel_dir)

        # Must ensure this is not a LIGOGPS as JSON won't understand it
        data_seg = segments.segment([int(data_seg[0]), int(data_seg[1])])
        fil.add_metadata('data_seg', data_seg)
        node.add_input_opt('--bank-file', parent)
        if df_parents is not None:
            node.add_input_list_opt('--frame-files', df_parents)

        return node

    def get_valid_times(self):
        """ Determine possible dimensions of needed input and valid output
        """

        if self.cp.has_option('workflow-matchedfilter',
                              'min-analysis-segments'):
            min_analysis_segs = int(self.cp.get('workflow-matchedfilter',
                                                'min-analysis-segments'))
        else:
            min_analysis_segs = 0

        if self.cp.has_option('workflow-matchedfilter',
                              'max-analysis-segments'):
            max_analysis_segs = int(self.cp.get('workflow-matchedfilter',
                                                'max-analysis-segments'))
        else:
            # Choose ridiculously large default value
            max_analysis_segs = 1000

        if self.cp.has_option('workflow-matchedfilter', 'min-analysis-length'):
            min_analysis_length = int(self.cp.get('workflow-matchedfilter',
                                                  'min-analysis-length'))
        else:
            min_analysis_length = 0

        if self.cp.has_option('workflow-matchedfilter', 'max-analysis-length'):
            max_analysis_length = int(self.cp.get('workflow-matchedfilter',
                                                  'max-analysis-length'))
        else:
            # Choose a ridiculously large default value
            max_analysis_length = 100000

        segment_length = int(self.get_opt('segment-length'))
        pad_data = 0
        if self.has_opt('pad-data'):
            pad_data += int(self.get_opt('pad-data'))

        # NOTE: Currently the tapered data is ignored as it is short and
        #       will lie within the segment start/end pad. This means that
        #       the tapered data *will* be used for PSD estimation (but this
        #       effect should be small). It will also be in the data segments
        #       used for SNR generation (when in the middle of a data segment
        #       where zero-padding is not being used) but the templates should
        #       not be long enough to use this data assuming segment start/end
        #       pad take normal values. When using zero-padding this data will
        #       be used for SNR generation.

        #if self.has_opt('taper-data'):
        #    pad_data += int(self.get_opt( 'taper-data' ))
        if self.has_opt('allow-zero-padding'):
            self.zero_padding=True
        else:
            self.zero_padding=False

        start_pad = int(self.get_opt( 'segment-start-pad'))
        end_pad = int(self.get_opt('segment-end-pad'))

        seg_ranges = range(min_analysis_segs, max_analysis_segs + 1)
        data_lengths = []
        valid_regions = []
        for nsegs in seg_ranges:
            analysis_length = (segment_length - start_pad - end_pad) * nsegs
            if not self.zero_padding:
                data_length = analysis_length + pad_data * 2 \
                              + start_pad + end_pad
                start = pad_data + start_pad
                end = data_length - pad_data - end_pad
            else:
                data_length = analysis_length + pad_data * 2
                start = pad_data
                end = data_length - pad_data
            if data_length > max_analysis_length: continue
            if data_length < min_analysis_length: continue
            data_lengths += [data_length]
            valid_regions += [segments.segment(start, end)]
        # If min_analysis_length is given, ensure that it is added as an option
        # for job analysis length.
        if min_analysis_length:
            data_length = min_analysis_length
            if not self.zero_padding:
                start = pad_data + start_pad
                end = data_length - pad_data - end_pad
            else:
                start = pad_data
                end = data_length - pad_data
            if end > start:
                data_lengths += [data_length]
                valid_regions += [segments.segment(start, end)]
        return data_lengths, valid_regions

    def zero_pad_data_extend(self, job_data_seg, curr_seg):
        """When using zero padding, *all* data is analysable, but the setup
        functions must include the padding data where it is available so that
        we are not zero-padding in the middle of science segments. This
        function takes a job_data_seg, that is chosen for a particular node
        and extends it with segment-start-pad and segment-end-pad if that
        data is available.
        """
        if self.zero_padding is False:
            return job_data_seg
        else:
            start_pad = int(self.get_opt( 'segment-start-pad'))
            end_pad = int(self.get_opt('segment-end-pad'))
            new_data_start = max(curr_seg[0], job_data_seg[0] - start_pad)
            new_data_end = min(curr_seg[1], job_data_seg[1] + end_pad)
            new_data_seg = segments.segment([new_data_start, new_data_end])
            return new_data_seg

# FIXME: This is probably misnamed, this is really GRBInspiralExectuable.
#        There's nothing coherent here, it's just that data segment stuff is
#        very different between GRB and all-sky/all-time
class PyCBCMultiInspiralExecutable(Executable):
    """
    The class responsible for setting up jobs for the
    pycbc_multi_inspiral executable.
    """
    current_retention_level = Executable.ALL_TRIGGERS

    # bank-veto-bank-file is a file input option for pycbc_multi_inspiral
    file_input_options = Executable.file_input_options + \
        ['--bank-veto-bank-file']

    def __init__(self, cp, name, ifo=None, injection_file=None,
                 gate_files=None, out_dir=None, tags=None):
        if tags is None:
            tags = []
        super().__init__(cp, name, ifo, out_dir=out_dir, tags=tags)
        self.injection_file = injection_file
        self.data_seg = segments.segment(int(cp.get('workflow', 'start-time')),
                                         int(cp.get('workflow', 'end-time')))
        self.num_threads = 1

    def create_node(self, data_seg, valid_seg, parent=None, inj_file=None,
                    dfParents=None, bankVetoBank=None, ipn_file=None,
                    slide=None, tags=None):
        if tags is None:
            tags = []
        node = Node(self)

        if not dfParents:
            raise ValueError("%s must be supplied with frame or cache files"
                              % self.name)

        # If doing single IFO search, make sure slides are disabled
        if len(self.ifo_list) < 2 and \
                (node.get_opt('--do-short-slides') is not None or \
                 node.get_opt('--short-slide-offset') is not None):
            raise ValueError("Cannot run with time slides in a single IFO "
                             "configuration! Please edit your configuration "
                             "file accordingly.")

        # Set instuments
        node.add_opt("--instruments", " ".join(self.ifo_list))

        pad_data = self.get_opt('pad-data')
        if pad_data is None:
            raise ValueError("The option pad-data is a required option of "
                             "%s. Please check the ini file." % self.name)

        # Feed in bank_veto_bank.xml, if given
        if self.cp.has_option('workflow-inspiral', 'bank-veto-bank-file'):
            node.add_input_opt('--bank-veto-bank-file', bankVetoBank)
        # Set time options
        node.add_opt('--gps-start-time', data_seg[0] + int(pad_data))
        node.add_opt('--gps-end-time', data_seg[1] - int(pad_data))
        node.add_opt('--trig-start-time', valid_seg[0])
        node.add_opt('--trig-end-time', valid_seg[1])
        node.add_opt('--trigger-time', self.cp.get('workflow', 'trigger-time'))

        # Set the input and output files
        node.new_output_file_opt(data_seg, '.hdf', '--output',
                                 tags=tags, store_file=self.retain_files)
        node.add_input_opt('--bank-file', parent, )

        if dfParents is not None:
            frame_arg = '--frame-files'
            for frame_file in dfParents:
                frame_arg += f" {frame_file.ifo}:{frame_file.name}"
                node.add_input(frame_file)
            node.add_arg(frame_arg)

        if ipn_file is not None:
            node.add_input_opt('--sky-positions-file', ipn_file)

        if inj_file is not None:
            if self.get_opt('--do-short-slides') is not None or \
                    self.get_opt('--short-slide-offset') is not None:
                raise ValueError("Cannot run with short slides in an "
                                 "injection job. Please edit your "
                                 "configuration file accordingly.")
            node.add_input_opt('--injection-file', inj_file)

        if slide is not None:
            for ifo in self.ifo_list:
                node.add_opt('--%s-slide-segment' % ifo.lower(), slide[ifo])

        # Channels
        channel_names = {}
        for ifo in self.ifo_list:
            channel_names[ifo] = self.cp.get_opt_tags(
                               "workflow", "%s-channel-name" % ifo.lower(), "")
        channel_names_str = \
            " ".join([val for key, val in channel_names.items()])
        node.add_opt("--channel-name", channel_names_str)

        return node

    def get_valid_times(self):
        pad_data = int(self.get_opt('pad-data'))
        if self.has_opt("segment-start-pad"):
            pad_data = int(self.get_opt("pad-data"))
            start_pad = int(self.get_opt("segment-start-pad"))
            end_pad = int(self.get_opt("segment-end-pad"))
            valid_start = self.data_seg[0] + pad_data + start_pad
            valid_end = self.data_seg[1] - pad_data - end_pad
        elif self.has_opt('analyse-segment-end'):
            safety = 1
            deadtime = int(self.get_opt('segment-length')) / 2
            spec_len = int(self.get_opt('inverse-spec-length')) / 2
            valid_start = (self.data_seg[0] + deadtime - spec_len + pad_data -
                           safety)
            valid_end = self.data_seg[1] - spec_len - pad_data - safety
        else:
            overlap = int(self.get_opt('segment-length')) / 4
            valid_start = self.data_seg[0] + overlap + pad_data
            valid_end = self.data_seg[1] - overlap - pad_data

        return self.data_seg, segments.segment(valid_start, valid_end)


class PyCBCTmpltbankExecutable(Executable):
    """ The class used to create jobs for pycbc_geom_nonspin_bank Executable and
    any other Executables using the same command line option groups.
    """

    current_retention_level = Executable.MERGED_TRIGGERS
    def __init__(self, cp, exe_name, ifo=None, out_dir=None,
                 tags=None, write_psd=False, psd_files=None):
        if tags is None:
            tags = []
        super().__init__(cp, exe_name, ifo, out_dir, tags=tags)
        self.cp = cp
        self.write_psd = write_psd
        self.psd_files = psd_files

    def create_node(self, data_seg, valid_seg, parent=None, df_parents=None, tags=None):
        if tags is None:
            tags = []
        node = Node(self)

        if not df_parents:
            raise ValueError("%s must be supplied with data file(s)"
                              % self.name)

        pad_data = int(self.get_opt('pad-data'))
        if pad_data is None:
            raise ValueError("The option pad-data is a required option of "
                             "%s. Please check the ini file." % self.name)

        # set the remaining option flags
        node.add_opt('--gps-start-time',
                     int_gps_time_to_str(data_seg[0] + pad_data))
        node.add_opt('--gps-end-time',
                     int_gps_time_to_str(data_seg[1] - pad_data))

        # set the input and output files
        # Add the PSD file if needed
        if self.write_psd:
            node.new_output_file_opt(valid_seg, '.txt', '--psd-output',
                                     tags=tags+['PSD_FILE'], store_file=self.retain_files)
        node.new_output_file_opt(valid_seg, '.xml.gz', '--output-file',
                                 tags=tags, store_file=self.retain_files)
        node.add_input_list_opt('--frame-files', df_parents)
        return node

    def create_nodata_node(self, valid_seg, tags=None):
        """ A simplified version of create_node that creates a node that does
        not need to read in data.

        Parameters
        -----------
        valid_seg : ligo.segments.segment
            The segment over which to declare the node valid. Usually this
            would be the duration of the analysis.

        Returns
        --------
        node : pycbc.workflow.core.Node
            The instance corresponding to the created node.
        """
        if tags is None:
            tags = []
        node = Node(self)

        # Set the output file
        # Add the PSD file if needed
        if self.write_psd:
            node.new_output_file_opt(valid_seg, '.txt', '--psd-output',
                                     tags=tags+['PSD_FILE'],
                                     store_file=self.retain_files)

        node.new_output_file_opt(valid_seg, '.xml.gz', '--output-file',
                                 store_file=self.retain_files)

        if self.psd_files is not None:
            should_add = False

            # If any of the ifos for this job are in the set
            # of ifos for which a static psd was provided.
            for ifo in self.ifo_list:
                for psd_file in self.psd_files:
                    if ifo in psd_file.ifo_list:
                        should_add = True

            if should_add:
                node.add_input_opt('--psd-file', psd_file)

        return node

    def get_valid_times(self):
        pad_data = int(self.get_opt( 'pad-data'))
        analysis_length = int(self.cp.get('workflow-tmpltbank',
                                          'analysis-length'))
        data_length = analysis_length + pad_data * 2
        start = pad_data
        end = data_length - pad_data
        return [data_length], [segments.segment(start, end)]


class LigolwAddExecutable(Executable):
    """ The class used to create nodes for the ligolw_add Executable. """

    current_retention_level = Executable.INTERMEDIATE_PRODUCT

    def create_node(self, jobSegment, input_files, output=None,
                    use_tmp_subdirs=True, tags=None):
        if tags is None:
            tags = []
        node = Node(self)

        # Very few options to ligolw_add, all input files are given as a long
        # argument list. If this becomes unwieldy we could dump all these files
        # to a cache file and read that in. ALL INPUT FILES MUST BE LISTED AS
        # INPUTS (with .add_input_opt_file) IF THIS IS DONE THOUGH!
        for fil in input_files:
            node.add_input_arg(fil)

        if output:
            node.add_output_opt('--output', output)
        else:
            node.new_output_file_opt(jobSegment, '.xml.gz', '--output',
                                    tags=tags, store_file=self.retain_files,
                                    use_tmp_subdirs=use_tmp_subdirs)
        return node


class PycbcSplitInspinjExecutable(Executable):
    """
    The class responsible for running the pycbc_split_inspinj executable
    """
    current_retention_level = Executable.INTERMEDIATE_PRODUCT

    def __init__(self, cp, exe_name, num_splits, ifo=None, out_dir=None):
        super().__init__(cp, exe_name, ifo, out_dir, tags=[])
        self.num_splits = int(num_splits)

    def create_node(self, parent, tags=None):
        if tags is None:
            tags = []
        node = Node(self)

        node.add_input_opt('--input-file', parent)

        if parent.name.endswith("gz"):
            ext = ".xml.gz"
        else:
            ext = ".xml"

        out_files = FileList([])
        for i in range(self.num_splits):
            curr_tag = 'split%d' % i
            curr_tags = parent.tags + [curr_tag]
            job_tag = parent.description + "_" + self.name.upper()
            out_file = File(parent.ifo_list, job_tag, parent.segment,
                            extension=ext, directory=self.out_dir,
                            tags=curr_tags, store_file=self.retain_files)
            out_files.append(out_file)

        node.add_output_list_opt('--output-files', out_files)
        return node


class LalappsInspinjExecutable(Executable):
    """
    The class used to create jobs for the lalapps_inspinj Executable.
    """
    current_retention_level = Executable.FINAL_RESULT
    extension = '.xml'
    def create_node(self, segment, exttrig_file=None, tags=None):
        if tags is None:
            tags = []
        node = Node(self)

        curr_tags = self.tags + tags
        # This allows the desired number of injections to be given explicitly
        # in the config file. Used for coh_PTF as segment length is unknown
        # before run time.
        if self.get_opt('write-compress') is not None:
            self.extension = '.xml.gz'

        # Check if these injections are using trigger information to choose
        # sky positions for the simulated signals
        if (self.get_opt('l-distr') == 'exttrig' and exttrig_file is not None \
                and 'trigger' in exttrig_file.description):
            # Use an XML file containing trigger information
            triggered = True
            node.add_input_opt('--exttrig-file', exttrig_file)
        elif (self.get_opt('l-distr') == 'ipn' and exttrig_file is not None \
                and 'IPN' in exttrig_file.description):
            # Use an IPN sky points file
            triggered = True
            node.add_input_opt('--ipn-file', exttrig_file)
        elif (self.get_opt('l-distr') != 'exttrig') \
                and (self.get_opt('l-distr') != 'ipn' and not \
                     self.has_opt('ipn-file')):
            # Use no trigger information for generating injections
            triggered = False
        else:
            err_msg = "The argument 'l-distr' passed to the "
            err_msg += "%s job has the value " % self.tagged_name
            err_msg += "'%s' but you have not " % self.get_opt('l-distr')
            err_msg += "provided the corresponding ExtTrig or IPN file. "
            err_msg += "Please check your configuration files and try again."
            raise ValueError(err_msg)

        if triggered:
            num_injs = int(self.cp.get_opt_tags('workflow-injections',
                                                'num-injs', curr_tags))
            inj_tspace = float(segment[1] - segment[0]) / num_injs
            node.add_opt('--time-interval', inj_tspace)
            node.add_opt('--time-step', inj_tspace)

        node.new_output_file_opt(segment, self.extension, '--output',
                                 store_file=self.retain_files)

        node.add_opt('--gps-start-time', int_gps_time_to_str(segment[0]))
        node.add_opt('--gps-end-time', int_gps_time_to_str(segment[1]))
        return node


class PycbcSplitBankExecutable(Executable):
    """ The class responsible for creating jobs for pycbc_hdf5_splitbank. """

    extension = '.hdf'
    current_retention_level = Executable.ALL_TRIGGERS
    def __init__(self, cp, exe_name, num_banks,
                 ifo=None, out_dir=None):
        super().__init__(cp, exe_name, ifo, out_dir, tags=[])
        self.num_banks = int(num_banks)

    def create_node(self, bank, tags=None):
        """
        Set up a CondorDagmanNode class to run splitbank code

        Parameters
        ----------
        bank : pycbc.workflow.core.File
            The File containing the template bank to be split

        Returns
        --------
        node : pycbc.workflow.core.Node
            The node to run the job
        """
        if tags is None:
            tags = []
        node = Node(self)
        node.add_input_opt('--bank-file', bank)

        # Get the output (taken from inspiral.py)
        out_files = FileList([])
        n_dp = math.ceil(math.log10(self.num_banks))
        for i in range( 0, self.num_banks):
            curr_tag = (f'bank%0{n_dp}d') % (i)
            # FIXME: What should the tags actually be? The job.tags values are
            #        currently ignored.
            curr_tags = bank.tags + [curr_tag] + tags
            job_tag = bank.description + "_" + self.name.upper()
            out_file = File(bank.ifo_list, job_tag, bank.segment,
                            extension=self.extension, directory=self.out_dir,
                            tags=curr_tags, store_file=self.retain_files)
            out_files.append(out_file)
        node.add_output_list_opt('--output-filenames', out_files)
        return node


class PycbcSplitBankXmlExecutable(PycbcSplitBankExecutable):
    """ Subclass resonsible for creating jobs for pycbc_splitbank. """

    extension='.xml.gz'


class PycbcConditionStrainExecutable(Executable):
    """ The class responsible for creating jobs for pycbc_condition_strain. """

    current_retention_level = Executable.ALL_TRIGGERS

    def create_node(self, input_files, tags=None):
        if tags is None:
            tags = []
        node = Node(self)
        start_time = self.cp.get("workflow", "start-time")
        end_time = self.cp.get("workflow", "end-time")
        node.add_opt('--gps-start-time', start_time)
        node.add_opt('--gps-end-time', end_time)
        node.add_input_list_opt('--frame-files', input_files)

        out_file = File(self.ifo, "gated",
                        segments.segment(int(start_time), int(end_time)),
                        directory=self.out_dir, store_file=self.retain_files,
                        extension=input_files[0].name.split('.', 1)[-1],
                        tags=tags)
        node.add_output_opt('--output-strain-file', out_file)

        out_gates_file = File(self.ifo, "output_gates",
                              segments.segment(int(start_time), int(end_time)),
                              directory=self.out_dir, extension='txt',
                              store_file=self.retain_files, tags=tags)
        node.add_output_opt('--output-gates-file', out_gates_file)

        return node, out_file


class PycbcCreateInjectionsExecutable(Executable):
    """ The class responsible for creating jobs
    for ``pycbc_create_injections``.
    """

    current_retention_level = Executable.ALL_TRIGGERS
    extension = '.hdf'

    def create_node(self, config_file=None, seed=None, tags=None):
        """ Set up a CondorDagmanNode class to run ``pycbc_create_injections``.

        Parameters
        ----------
        config_file : pycbc.workflow.core.File
            A ``pycbc.workflow.core.File`` for inference configuration file
            to be used with ``--config-files`` option.
        seed : int
            Seed to use for generating injections.
        tags : list
            A list of tags to include in filenames.

        Returns
        --------
        node : pycbc.workflow.core.Node
            The node to run the job.
        """

        # default for tags is empty list
        tags = [] if tags is None else tags

        # get analysis start and end time
        start_time = self.cp.get("workflow", "start-time")
        end_time = self.cp.get("workflow", "end-time")
        analysis_time = segments.segment(int(start_time), int(end_time))

        # make node for running executable
        node = Node(self)
        if config_file is not None:
            node.add_input_opt("--config-files", config_file)
        if seed:
            node.add_opt("--seed", seed)
        injection_file = node.new_output_file_opt(analysis_time,
                                                  self.extension,
                                                  "--output-file",
                                                  tags=tags)

        return node, injection_file


class PycbcInferenceExecutable(Executable):
    """ The class responsible for creating jobs for ``pycbc_inference``.
    """

    current_retention_level = Executable.ALL_TRIGGERS

    def create_node(self, config_file, seed=None, tags=None,
                    analysis_time=None):
        """ Set up a pegasus.Node instance to run ``pycbc_inference``.

        Parameters
        ----------
        config_file : pycbc.workflow.core.File
            A ``pycbc.workflow.core.File`` for inference configuration file
            to be used with ``--config-files`` option.
        seed : int
            An ``int`` to be used with ``--seed`` option.
        tags : list
            A list of tags to include in filenames.

        Returns
        --------
        node : pycbc.workflow.core.Node
            The node to run the job.
        """
        # default for tags is empty list
        tags = [] if tags is None else tags
        # if analysis time not provided, try to get it from the config file
        if analysis_time is None:
            start_time = self.cp.get("workflow", "start-time")
            end_time = self.cp.get("workflow", "end-time")
            analysis_time = segments.segment(int(start_time), int(end_time))
        # make node for running executable
        node = Node(self)
        node.add_input_opt("--config-file", config_file)
        if seed is not None:
            node.add_opt("--seed", seed)
        inference_file = node.new_output_file_opt(analysis_time,
                                                  ".hdf", "--output-file",
                                                  tags=tags)
        if self.cp.has_option("pegasus_profile-inference",
                              "condor|+CheckpointSig"):
            err_msg = "This is not yet supported/tested with pegasus 5. "
            err_msg += "Please reimplement this (with unittest :-) )."
            raise ValueError(err_msg)
            #ckpt_file_name = "{}.checkpoint".format(inference_file.name)
            #ckpt_file = dax.File(ckpt_file_name)
            # DO NOT call pegasus API stuff outside of
            # pegasus_workflow.py.
            #node._dax_node.uses(ckpt_file, link=dax.Link.OUTPUT,
            #                    register=False, transfer=False)

        return node, inference_file


class PycbcHDFSplitInjExecutable(Executable):
    """ The class responsible for creating jobs for ``pycbc_hdf_splitinj``.
    """
    current_retention_level = Executable.ALL_TRIGGERS

    def __init__(self, cp, exe_name, num_splits, ifo=None, out_dir=None):
        super().__init__(cp, exe_name, ifo, out_dir, tags=[])
        self.num_splits = int(num_splits)

    def create_node(self, parent, tags=None):
        if tags is None:
            tags = []
        node = Node(self)
        node.add_input_opt('--input-file', parent)
        out_files = FileList([])
        for i in range(self.num_splits):
            curr_tag = 'split%d' % i
            curr_tags = parent.tags + [curr_tag]
            job_tag = parent.description + "_" + self.name.upper()
            out_file = File(parent.ifo_list, job_tag, parent.segment,
                            extension='.hdf', directory=self.out_dir,
                            tags=curr_tags, store_file=self.retain_files)
            out_files.append(out_file)
        node.add_output_list_opt('--output-files', out_files)
        return node
