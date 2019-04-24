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
package org.phenotips.test.deployment.rest.internal;

import org.phenotips.data.indexing.PatientIndexer;
import org.phenotips.test.deployment.rest.PatientReindexResource;

import org.xwiki.component.annotation.Component;
import org.xwiki.rest.XWikiResource;

import javax.inject.Inject;
import javax.inject.Named;
import javax.inject.Singleton;
import javax.ws.rs.core.Response;


/**
 * Default implementation of the {@link PatientReindexResource}.
 *
 * @version $Id$
 * @since 1.1
 */
@Component
@Named("org.phenotips.test.deployment.rest.internal.DefaultPatientReindexResource")
@Singleton
public class DefaultPatientReindexResource extends XWikiResource implements PatientReindexResource
{
    @Inject
    private PatientIndexer indexer;

    @Override
    public Response reindexPatients()
    {
        try {
            this.indexer.reindex();
            return Response.status(Response.Status.OK).build();
        } catch (final IndexOutOfBoundsException e) {
            this.slf4Jlogger.error("Error while reindexing patients: {}", e);
            return Response.status(Response.Status.BAD_REQUEST).build();
        }
    }
}
