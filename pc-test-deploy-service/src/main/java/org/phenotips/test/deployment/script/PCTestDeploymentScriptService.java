/*
 * See the NOTICE file distributed with this work for additional
 * information regarding copyright ownership.
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public License
 * along with this program.  If not, see http://www.gnu.org/licenses/
 */
package org.phenotips.test.deployment.script;

import org.xwiki.component.annotation.Component;
import org.xwiki.script.service.ScriptService;
import org.xwiki.stability.Unstable;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileReader;

import javax.inject.Inject;
import javax.inject.Named;
import javax.inject.Singleton;

import org.apache.commons.lang3.StringUtils;
import org.json.JSONArray;
import org.slf4j.Logger;

/**
 * Allows to call Python deployment script for spinning OpenStack VM for customized PhenomeCentral build.
 *
 * @version $Id: d9a7db2d905d386d7e8ff3878095b0ec6c61db32 $
 * @since 1.2
 */
@Unstable
@Component
@Named("pcTestDeployment")
@Singleton
public class PCTestDeploymentScriptService implements ScriptService
{
    @Inject
    private Logger logger;

    /** Python script file. **/
    private final String scriptFile = "openstack_vm_deploy.py";

    /** Text file holding OpenStack running servers info JSON. **/
    private final String serversFile = "server_list.txt";

    /**
     * Runs Python script with parameters.
     *
     * @param pnBrnachName Patient-Network GitHub repository branch name
     * @param rmBrnachName Remote-Matching GitHub repository branch name
     * @param pcBrnachName PhenomeCentral GitHub repository branch name
     * @param buildName user-defined PhenomeCentral test build name
     * @return true if the VM has successfully started up
     */
    @SuppressWarnings({ "checkstyle:NPathComplexity", "checkstyle:CyclomaticComplexity" })
    public boolean runDeploymentScript(String pnBrnachName, String rmBrnachName, String pcBrnachName, String buildName)
    {
        try {
            File f = new File(this.scriptFile);
            if (!f.exists() || f.isDirectory()) {
                this.logger.error("No such file {}", this.scriptFile);
                return false;
            }

            String command = "python " + this.scriptFile + " --start";
            if (pnBrnachName != null && StringUtils.isNotBlank(pnBrnachName)) {
                command = command + " --pn " + pnBrnachName;
            }
            if (rmBrnachName != null && StringUtils.isNotBlank(rmBrnachName)) {
                command = command + " --rm " + rmBrnachName;
            }
            if (pcBrnachName != null && StringUtils.isNotBlank(pcBrnachName)) {
                command = command + " --pc " + pcBrnachName;
            }
            if (buildName != null && StringUtils.isNotBlank(buildName)) {
                command = command + " --build_name " + buildName;
            }

            Process p = Runtime.getRuntime().exec(command);
            int retcode = p.waitFor();
            if (retcode == 0) {
                return true;
            }
        } catch (Exception ex) {
            this.logger.error("Error executing deployment script: {}", ex);
        }
        return false;
    }

    /**
     * List OpenStack server instances in the JSON file.
     *
     * @return JSON string with servers info or empty string if fetching is unsuccessful.
     */
    public JSONArray listServers()
    {
        try {
            File f = new File(this.scriptFile);
            if (!f.exists() || f.isDirectory()) {
                this.logger.error("No such file {}", this.scriptFile);
                return null;
            }

            String command = "python " + this.scriptFile + " --action list";
            Process p = Runtime.getRuntime().exec(command);
            int retcode = p.waitFor();
            if (retcode == 0) {
                String serversInfo = "";

                BufferedReader in = new BufferedReader(new FileReader(this.serversFile));
                String line;

                while ((line = in.readLine()) != null) {
                    serversInfo += line;
                }

                return new JSONArray(serversInfo);
            }
        } catch (Exception ex) {
            this.logger.error("OpenStack server instances : {}", ex);
        }
        return null;
    }

    /**
     * Delete OpenStack server instance specified by name.
     *
     * @param name name of the server to delete
     * @return true if the servers was successfully deleted
     */
    public boolean deleteServer(String name)
    {
        try {
            File f = new File(this.scriptFile);
            if (!f.exists() || f.isDirectory()) {
                this.logger.error("No such file {}", this.scriptFile);
                return false;
            }

            String command = "python " + this.scriptFile + " --delete";
            if (name == null || StringUtils.isBlank(name)) {
                return false;
            }

            command = command + " --build_name " + name;
            Process p = Runtime.getRuntime().exec(command);
            int retcode = p.waitFor();
            if (retcode == 0) {
                return true;
            }
        } catch (Exception ex) {
            this.logger.error("OpenStack server instances : {}", ex);
        }
        return false;
    }
}
