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
import java.io.FileNotFoundException;
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
    private static final boolean IS_WINDOWS = (System.getProperty("os.name").toLowerCase().indexOf("win") >= 0);

    // In Windows it is easier to manually specify the interpreter for the script
    //
    // Linux can run python scripts directly using a header like "#!/usr/bin/env python3.6". At the same time in Linux
    // it is harder to know the exact interpreter to be used, e.g. "python", "python3.6", or something else.
    private static final String EXECUTION_PREFIX = IS_WINDOWS ? "python " : "./";

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
            this.logger.error("Running deployment script for branches PN[{}], RM[{}], PC[{}]",
                pnBrnachName, rmBrnachName, pcBrnachName);

            String scriptArguments = " --action deploy";
            if (pnBrnachName != null && StringUtils.isNotBlank(pnBrnachName)) {
                scriptArguments = scriptArguments + " --pn " + pnBrnachName;
            }
            if (rmBrnachName != null && StringUtils.isNotBlank(rmBrnachName)) {
                scriptArguments = scriptArguments + " --rm " + rmBrnachName;
            }
            if (pcBrnachName != null && StringUtils.isNotBlank(pcBrnachName)) {
                scriptArguments = scriptArguments + " --pc " + pcBrnachName;
            }
            if (buildName != null && StringUtils.isNotBlank(buildName)) {
                scriptArguments = scriptArguments + " --build-name " + buildName;
            }

            // execute the script, expected return code is 0
            return executeScript(scriptArguments, 0);
        } catch (Exception ex) {
            this.logger.error("Error executing deployment script: {}", ex);
        }
        return false;
    }

    /**
     * List OpenStack server instances in the JSON file.
     *
     * @return JSON array with server info or null if fetching is unsuccessful.
     */
    public JSONArray listServers()
    {
        try {
            this.logger.error("Getting the list of already running VMs");

            String scriptArguments = " --action list";

            // execute the script, expected return code is 0
            if (executeScript(scriptArguments, 0)) {
                this.logger.error("* attempting to parse server list file [{}]", this.serversFile);

                String serversInfo = "";
                BufferedReader in = new BufferedReader(new FileReader(this.serversFile));

                String line;
                while ((line = in.readLine()) != null) {
                    serversInfo += line;
                }

                return new JSONArray(serversInfo);
            }
        } catch (FileNotFoundException ex) {
            this.logger.error("Error: script did not generate serverlist file [{}] or the file could not be found",
                this.serversFile);
        } catch (Exception ex) {
            this.logger.error("Error executing server list script: {}", ex);
        }
        return null;
    }

    /**
     * Delete OpenStack server instance specified by name.
     *
     * @param buildName name of the server to delete
     * @return true if the servers was successfully deleted
     */
    public boolean deleteServer(String buildName)
    {
        try {
            this.logger.error("Removing existing VM for build [{}]", buildName);

            if (buildName == null || StringUtils.isBlank(buildName)) {
                return false;
            }

            String scriptArguments = " --action delete --build-name " + buildName;

            // execute the script, expected return code is 0
            return executeScript(scriptArguments, 0);
        } catch (Exception ex) {
            this.logger.error("Error removing VM for build [{}] : {}", buildName, ex);
        }
        return false;
    }

    private boolean executeScript(String scriptArguments, int expectedReturnCode) throws Exception
    {
        try {
            this.logger.error("Script arguments to be used: [{}]", scriptArguments);
            this.logger.error(" * expected script location: [{}]", System.getProperty("user.dir"));
            this.logger.error(" * expected script filename: [{}]", this.scriptFile);

            File f = new File(this.scriptFile);
            if (!f.exists() || f.isDirectory()) {
                this.logger.error("Script file [{}] not found", this.scriptFile);
                return false;
            }

            Process p;
            if (this.IS_WINDOWS) {
                String fullCommand = this.EXECUTION_PREFIX + this.scriptFile + scriptArguments;
                this.logger.error("- full command to be executed: [{}]", fullCommand);
                p = Runtime.getRuntime().exec(fullCommand);
            } else {
                // we need OpenStack environemnt variables to be available, which in Linux  means explicitly
                // invoking bash with a "--login" parameter to force sourcing profile.d scripts
                // FIXME: maybe there is an easier way? Tried a few other options and they did not work
                String[] cmdArray = { "/bin/bash", "--login", "-c",
                                      this.EXECUTION_PREFIX + this.scriptFile + scriptArguments };
                this.logger.error(" * full command to be executed: [{}]", String.join(" ", cmdArray));
                p = Runtime.getRuntime().exec(cmdArray);
            }
            int retcode = p.waitFor();
            this.logger.error("Execution finished with return code {}", retcode);

            if (retcode == expectedReturnCode) {
                return true;
            }
        } catch (Exception ex) {
            this.logger.error("Error executing deployment script");
            throw ex;
        }
        return false;
    }
}

