import yaml
import os
from collections import namedtuple


DiagFileEntry = namedtuple('DiagFileEntry',
                    ("output_freq", "output_freq_units", "file_format", "time_axis_units",
                     "time_axis_name", "new_file_freq", "new_file_freq_units", "start_time",
                     "file_duration", "file_duration_units"))
DiagFieldEntry = namedtuple('DiagFieldEntry',
                    ("module_name", "output_name", "file_name", "time_sampling", "reduction_method",
                     "regional_section", "packing"))

class CaseDiags(object,):

    def __init__(self, diag_config_yml_path):

        # load diag_config.yml file:
        self.config = yaml.load(open(diag_config_yml_path,'r'), Loader=yaml.Loader)

        # check if required keywords are in diag_config.yml
        reqd_kws = ['rundir']
        for kw in reqd_kws:
            assert kw in self.config, "The required keyword "+kw+" not in diag_config file"

    def _parse_diag_table(self):
        diag_table_path = os.path.join(self.config['rundir'], 'diag_table')

        with open(diag_table_path,'r') as diag_table:

            # first read the two header files:
            ctr = 0
            for line in diag_table:
                line = line.strip()
                if len(line)>0 and line[0] != '#': # not an empty line or comment line
                    ctr+=1
                    if ctr==2: break

            # now read the file and field blocks
            self.diag_files = dict()
            self.diag_fields = dict()
            within_file_list = True # if false, within field list
            for line in diag_table: 
                line = line.strip()
                line = line.replace("'"," ").replace('"',' ').replace(",","")
                line_split = line.split()
                if len(line)>0 and line[0] != '#': # not an empty line or comment line

                    if len(line)>11 and line[1:12]=="ocean_model":
                        within_file_list = False
                        
                    if within_file_list:
                        file_name = line_split[0]
                        self.diag_files[file_name] = DiagFileEntry(
                            output_freq = line_split[1],
                            output_freq_units = line_split[2],
                            file_format = line_split[3],
                            time_axis_units = line_split[4],
                            time_axis_name = line_split[5],
                            new_file_freq = line_split[6] if len(line_split)>6 else None,
                            new_file_freq_units = line_split[7] if len(line_split)>7 else None,
                            start_time = line_split[8] if len(line_split)>8 else None,
                            file_duration = line_split[9] if len(line_split)>9 else None,
                            file_duration_units = line_split[10] if len(line_split)>10 else None
                        )
                                                
                    else: # within field list
                        field_name = line_split[1]
                        self.diag_fields[field_name] = DiagFieldEntry(
                            module_name = line_split[0],
                            output_name = line_split[2],
                            file_name = line_split[3],
                            time_sampling = line_split[4],
                            reduction_method = line_split[5],
                            regional_section = line_split[6],
                            packing = line_split[7])

config_yml_path = "/glade/work/altuntas/mom6.diags/g.c2b6.GJRA.TL319_t061.long_JRA_mct.001/diag_config.yml"

case_diags = CaseDiags(config_yml_path)
case_diags._parse_diag_table()
for entry in case_diags.diag_files:
    print(entry,case_diags.diag_files[entry])
