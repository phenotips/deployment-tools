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
import java.io.IOException;

import javax.inject.Inject;
import javax.inject.Named;
import javax.inject.Singleton;

import org.apache.commons.lang3.StringUtils;
import org.json.JSONArray;
import org.json.JSONObject;
import org.slf4j.Logger;

/**
 * Allows spinning, monitoring and managing OpenStack VMs for customized test PhenomeCentral builds via Python scripts.
 *
 * @version $Id$
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
    // Linux can run Python scripts directly using a header like "#!/usr/bin/env python3.6". At the same time in Linux
    // it is harder to know the exact interpreter to be used, e.g. "python", "python3.6", or something else.
    private static final String EXECUTION_PREFIX = IS_WINDOWS ? "python " : "./";

    @Inject
    private Logger logger;

    /** Python script file for spinning OpenStack VM. **/
    private final String scriptFile = "openstack_vm_deploy.py";

    /** Python script file to load test data. **/
    private final String scriptLoadDataFile = "load_test_data.py";

    /** Text file holding OpenStack running servers info JSON. **/
    private final String serversFile = "server_list.txt";

    /** Text file holding test datasets directories names. **/
    private final String datasetsFile = "datasets_list.txt";

    /**
     * Runs Python script with parameters.
     *
     * @param pnBrnachName Patient Network GitHub repository branch name (optional, defaults to "master")
     * @param rmBrnachName Remote Matching GitHub repository branch name (optional, defaults to "master")
     * @param pcBrnachName PhenomeCentral GitHub repository branch name (optional, defaults to "master")
     * @param ptBrnachName PhenoTips GitHub repository branch name (optional, defaults to "master")
     * @param buildName user-defined PhenomeCentral test build name
     *     (optional, defaults to "master" if first 3 parameters are not specified,
     *     or composed of them in a form of "pnBrnachName_rmBrnachName_pcBrnachName")
     * @param project PhenomeCentral or PhenoTips (optional, defaults to "PhenomeCentral")
     * @return true if the VM has successfully started up
     */
    @SuppressWarnings({ "checkstyle:NPathComplexity", "checkstyle:CyclomaticComplexity" })
    public boolean deploy(String pnBrnachName, String rmBrnachName, String pcBrnachName, String ptBrnachName,
        String buildName, String project)
    {
        try {
            this.logger.error("Running deployment script for branches PN[{}], RM[{}], PC[{}]",
                pnBrnachName, rmBrnachName, pcBrnachName);

            String scriptArguments = " --action deploy";
            if (StringUtils.isNotBlank(pnBrnachName)) {
                scriptArguments = scriptArguments + " --pn " + pnBrnachName;
            }
            if (StringUtils.isNotBlank(rmBrnachName)) {
                scriptArguments = scriptArguments + " --rm " + rmBrnachName;
            }
            if (StringUtils.isNotBlank(pcBrnachName)) {
                scriptArguments = scriptArguments + " --pc " + pcBrnachName;
            }
            if (StringUtils.isNotBlank(ptBrnachName)) {
                scriptArguments = scriptArguments + " --pt " + ptBrnachName;
            }
            if (StringUtils.isNotBlank(buildName)) {
                scriptArguments = scriptArguments + " --build-name " + buildName;
            }
            if (StringUtils.isNotBlank(project)) {
                scriptArguments = scriptArguments + " --project " + project;
            }

            // execute the script, expected return code is 0
            return executeScript(this.scriptFile, scriptArguments, 0);
        } catch (Exception ex) {
            this.logger.error("Error executing deployment script: {}", ex);
        }
        return false;
    }

    /**
     * List OpenStack server instances and resources usage stats in the JSON format in txt file.
     *
     * @return JSON array with server info or null if fetching is unsuccessful.
     */
    public JSONObject listServers()
    {
        try {
            this.logger.error("Getting the list of already running VMs");

            String scriptArguments = " --action list";

            // execute the script, expected return code is 0
            if (executeScript(this.scriptFile, scriptArguments, 0)) {
                this.logger.error("* attempting to parse server list file [{}]", this.serversFile);

                String serversInfo = readFile(this.serversFile);

                return new JSONObject(serversInfo);
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

            if (StringUtils.isBlank(buildName)) {
                return false;
            }

            String scriptArguments = " --action delete --build-name " + buildName;

            // execute the script, expected return code is 0
            return executeScript(this.scriptFile, scriptArguments, 0);
        } catch (Exception ex) {
            this.logger.error("Error removing VM for build [{}] : {}", buildName, ex);
        }
        return false;
    }

    /**
     * Load test data to server instance specified by IP.
     *
     * @param ip the IP address of the server to load data to
     * @param dataName name of the test data directory
     * @return true if the data was successfully loaded
     */
    public boolean loadTestData(String ip, String dataName)
    {
        try {
            this.logger.error("Loading test data to VM with IP [{}]", ip);

            if (StringUtils.isBlank(ip) || StringUtils.isBlank(dataName)) {
                return false;
            }

            String scriptArguments = " --action upload-dataset --ip " + ip + " --dataset-name " + dataName;

            // execute the script, expected return code is 0
            return executeScript(this.scriptLoadDataFile, scriptArguments, 0);
        } catch (Exception ex) {
            this.logger.error("Error loading test data [{}] to VM with IP [{}] : {}", dataName, ip, ex);
        }
        return false;
    }

    /**
     * List test datasets directories names.
     *
     * @return JSONArray with list of strings that represent directory names with test data.
     */
    public JSONArray listTestDatasets()
    {
        try {
            this.logger.error("Getting the list of test datasets directories");

            String scriptArguments = " --action list-datasets";

            // execute the script, expected return code is 0
            if (executeScript(this.scriptLoadDataFile, scriptArguments, 0)) {
                this.logger.error("* attempting to parse test datasets list file [{}]", this.datasetsFile);

                String datasets = readFile(this.datasetsFile);
                return new JSONArray(datasets);
            }
        } catch (FileNotFoundException ex) {
            this.logger.error(
                "Error: script did not generate test datasets list file [{}] or the file could not be found",
                this.datasetsFile);
        } catch (Exception ex) {
            this.logger.error("Error executing test datasets list script: {}", ex);
        }
        return null;
    }

    private String readFile(String fileName) throws IOException
    {
        String data = "";
        BufferedReader in = new BufferedReader(new FileReader(fileName));

        String line;
        while ((line = in.readLine()) != null) {
            data += line;
        }
        in.close();

        return data;
    }

    private boolean executeScript(String scriptFileName, String scriptArguments, int expectedReturnCode)
        throws Exception
    {
        try {
            this.logger.error("Script arguments to be used: [{}]", scriptArguments);
            this.logger.error(" * expected script location: [{}]", System.getProperty("user.dir"));
            this.logger.error(" * expected script filename: [{}]", scriptFileName);

            File f = new File(scriptFileName);
            if (!f.exists() || f.isDirectory()) {
                this.logger.error("Script file [{}] not found", scriptFileName);
                return false;
            }

            Process p;
            if (IS_WINDOWS) {
                String fullCommand = EXECUTION_PREFIX + scriptFileName + scriptArguments;
                this.logger.error("- full command to be executed: [{}]", fullCommand);
                p = Runtime.getRuntime().exec(fullCommand);
            } else {
                // we need OpenStack environment variables to be available, which in Linux means explicitly
                // invoking bash with a "--login" parameter to force sourcing profile.d scripts
                // FIXME: maybe there is an easier way? Tried a few other options and they did not work
                String[] cmdArray =
                { "/bin/bash", "--login", "-c", EXECUTION_PREFIX + scriptFileName + scriptArguments };
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
