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
package org.phenotips.test.deployment.rest;

import org.phenotips.data.rest.PatientResource;
import org.phenotips.rest.ParentResource;

import org.xwiki.stability.Unstable;

import javax.ws.rs.GET;
import javax.ws.rs.Path;
import javax.ws.rs.Produces;
import javax.ws.rs.core.MediaType;
import javax.ws.rs.core.Response;

/**
 * Reindex patients. Needed because Solr does not triggered on XAR import and imported patients are not indexed.
 *
 * @version $Id$
 * @since 1.1
 */
@Unstable("New API introduced in 1.2")
@Path("/patients/reindex")
@ParentResource(PatientResource.class)
public interface PatientReindexResource
{
    /**
     * Reindex patients.
     *
     * @return a response
     */
    @GET
    @Produces(MediaType.APPLICATION_JSON)
    Response reindexPatients();
}
