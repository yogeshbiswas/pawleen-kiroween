# Requirements Document

## Introduction

Pawleen is a haunted Halloween photo booth web application that dresses pets in costumes. A visitor uploads a pet photo, chooses a costume (by uploading a costume photo or typing a description), and summons a costume. A multi-agent pipeline (Gatekeeper, Costume Maker, Quality Checker) built on the OpenAI API validates the inputs, generates the costumed pet image against a spooky Halloween scene, and verifies the result. The visitor watches live progress, downloads or shares the result, and keeps a private Haunted Gallery stored in the visitor's own browser.

The backend uses Python and FastAPI. The frontend uses HTML, Tailwind CSS, and vanilla JavaScript served by FastAPI. The application deploys as a single Render web service. Secrets live only in a `.env` file. The application is a Kiroween 2026 Costume Contest entry, so a polished, haunting, mobile-first UI is a primary goal.

Design principles that apply to every requirement:

- Flexibility: if the AI can see a pet, Pawleen uses it. The Frontend fixes inputs automatically (orientation, size) instead of rejecting them. Pawleen rejects an input only when the file is not an image, no animal is present, or the content is harmful.
- Timing: Pawleen avoids tight hard time limits. Each AI step has a generous timeout. The Gatekeeper_Agent and Quality_Checker_Agent each get one automatic Silent_Retry. The Costume_Maker_Agent gets no automatic retry on timeout, so that the operator does not pay twice. The whole Agent_Pipeline has a Pipeline_Timeout of 180 seconds. Pure UI update targets (for example, updating the screen within 1 second) remain fixed.
- Fair counting: a failed, timed-out, rejected, or refused request is never counted against the Visitor_Daily_Limit, the Judge_Daily_Limit, or the Global_Daily_Cap.
- Tone: every user-facing message is a Spooky_Message that also states the plain action the Visitor can take.

Out of scope: user accounts, shopping cart, payments, and any database or server-side storage of user images.

## Glossary

- **Pawleen_App**: The complete web application, comprising the Backend and the Frontend.
- **Backend**: The Python FastAPI service that serves the Frontend, enforces limits, and runs the Agent_Pipeline.
- **Frontend**: The HTML, Tailwind CSS, and vanilla JavaScript user interface served by the Backend.
- **Visitor**: A person using the Pawleen_App in a web browser.
- **Browser_ID**: A random, opaque identifier stored in a cookie issued by the Backend, containing no personal data, used to identify a browser for limit counting and Judge_Pass attempt counting.
- **Judge**: A Visitor who presents a valid Judge_Pass.
- **Pet_Photo**: An image uploaded by the Visitor that is intended to show a real animal.
- **Costume_Photo**: An optional image uploaded by the Visitor that gives a costume idea, such as clothing, accessories, a person or character in costume, or a drawing.
- **Costume_Description**: Text typed by the Visitor that describes the costume to apply, with a maximum of 200 characters.
- **Costume_Request**: The combination of one Pet_Photo and either one Costume_Photo or one Costume_Description, or both.
- **Prepared_Image**: A Pet_Photo or Costume_Photo after the Frontend has applied EXIF orientation correction and, where needed, downscaling and compression.
- **Example_Chip**: A clickable UI element that fills the Costume_Description with a sample costume idea.
- **Agent_Pipeline**: The ordered sequence of Gatekeeper_Agent, Costume_Maker_Agent, and Quality_Checker_Agent.
- **Gatekeeper_Agent**: The agent that uses a vision-capable OpenAI model to validate the Costume_Request before any image generation call.
- **Costume_Maker_Agent**: The agent that uses an OpenAI image editing model to generate the Costumed_Image.
- **Quality_Checker_Agent**: The agent that uses a vision-capable OpenAI model to verify the Costumed_Image.
- **Silent_Retry**: One automatic repeat of a failed or timed-out Gatekeeper_Agent or Quality_Checker_Agent call, performed without any message to the Visitor.
- **Regeneration**: One additional Costume_Maker_Agent call triggered by a failed Quality_Checker_Agent check. A Regeneration is not a Silent_Retry.
- **Pipeline_Timeout**: The maximum total duration of the Agent_Pipeline for one Costume_Request, which is 180 seconds.
- **Costumed_Image**: The generated portrait image showing the pet wearing the costume in front of a Spooky_Scene.
- **Spooky_Scene**: A Halloween background setting for the Costumed_Image, such as a magical library with floating candles, a dark castle under a red moon, a foggy pumpkin patch at night, a ghost ship on a stormy sea, or a misty graveyard with fireflies.
- **Pipeline_Step**: One named stage of the Agent_Pipeline reported to the Visitor (gatekeeping, costume brewing, quality checking).
- **Heartbeat_Event**: A progress event sent by the Backend to the Frontend at least every 10 seconds while the Agent_Pipeline runs, which carries no step change.
- **Progress_Screen**: The Frontend view that shows Pipeline_Step status as the Agent_Pipeline runs.
- **Result_View**: The Frontend view that shows the Costumed_Image, the Before_After_View, and the result actions.
- **Before_After_View**: A Result_View display that shows the original Pet_Photo next to the Costumed_Image.
- **Haunted_Gallery**: The Frontend view listing the Visitor's saved Costumed_Images.
- **Browser_Storage**: IndexedDB in the Visitor's own browser, used to store Haunted_Gallery contents.
- **Preference_Storage**: Small flag storage in the Visitor's own browser (such as localStorage), used only for the Privacy_Banner dismissal and the Sound_Toggle setting, never for images.
- **Session_Storage**: Browser storage that is cleared when the browser session ends.
- **Privacy_Banner**: A friendly, dismissible notice shown on the first visit that explains how photos are handled.
- **Sound_Toggle**: A UI control that turns optional spooky sound effects on or off.
- **Visitor_Daily_Limit**: The maximum number of generations allowed per Browser_ID per day for non-Judge Visitors, read from the environment with a default of 3.
- **Global_Daily_Cap**: The maximum number of generations allowed across all non-Judge Visitors per day, configured in the environment.
- **Judge_Pass**: A secret code read from the `.env` file and presented through the `pass` URL query parameter or the Judge_Pass_Box.
- **Judge_Pass_Box**: A small UI input labeled "Have a judge pass?" for entering a Judge_Pass.
- **Judge_Daily_Limit**: The separate, larger per-day generation allowance for each Judge, counted per Browser_ID, read from the environment with a default of 20.
- **Environment_Config**: Values read from the `.env` file or process environment, including the OpenAI API key, Judge_Pass, model names, and limit values.
- **Spooky_Message**: A user-facing message written in a friendly Halloween tone that remains clear about what happened and what to do next.
- **Usage_Day**: One calendar day measured in UTC. The Backend resets counts at the end of the Usage_Day, and the Frontend shows reset times only as relative durations.

## Requirements

### Requirement 1: Pet Photo Upload

**User Story:** As a Visitor, I want to upload or take a photo of my pet without worrying about size or orientation, so that Pawleen can dress my pet in a costume.

#### Acceptance Criteria

1. THE Frontend SHALL provide a Pet_Photo upload control that accepts files with the JPEG, PNG, or WebP image type.
2. WHERE the Visitor's device is a mobile device with a camera, THE Frontend SHALL let the Visitor either take a new photo with the camera or choose an existing photo for the Pet_Photo.
3. WHEN the Visitor selects a valid Pet_Photo, THE Frontend SHALL immediately display the message "🕯️ Developing your photo in the darkroom...", and SHALL then display a preview of the Prepared_Image within 3 seconds on a typical phone.
4. WHEN the Visitor selects a Pet_Photo that has an EXIF orientation, THE Frontend SHALL correct the orientation in both the preview and the uploaded Prepared_Image.
5. WHEN the Visitor selects a Pet_Photo larger than 10 MB (10,485,760 bytes) or larger than 2048 pixels on its longest side, THE Frontend SHALL downscale and compress the image in the browser to at most 2048 pixels on the longest side and below 10 MB before upload, and SHALL accept the Pet_Photo without rejecting it.
6. WHEN the Visitor selects a Pet_Photo whose shorter side is below 512 pixels, THE Frontend SHALL accept the Pet_Photo and display the note "Small photo, the result may be a bit blurry 🌙".
7. THE Frontend SHALL display the tip "Works best with one pet per photo 🐾" near the Pet_Photo upload control and SHALL accept a Pet_Photo that shows more than one pet.
8. IF the Visitor selects a file that is not a JPEG, PNG, or WebP image, THEN THE Frontend SHALL reject the file, retain any previously selected Pet_Photo and its preview unchanged, and display the Spooky_Message "The spirits can only read photos 📸 Please choose a JPG, PNG or WebP image."
9. IF the Visitor selects a zero-byte file, a file that cannot be decoded as an image, or an image that the Frontend cannot reduce to below 10 MB, THEN THE Frontend SHALL reject the file, retain any previously selected Pet_Photo and its preview unchanged, and display a Spooky_Message indicating that the file could not be read as an image and asking the Visitor to choose a different photo.
10. WHEN the Visitor selects a new valid Pet_Photo, THE Frontend SHALL replace the previous Pet_Photo and its preview with the new one, so that exactly one Pet_Photo is selected at any time.
11. WHEN the Visitor selects the remove action for the selected Pet_Photo before submission, THE Frontend SHALL clear the Pet_Photo and its preview, and return the upload control to its initial state with no Pet_Photo selected.
12. WHEN a Spooky_Message is displayed for a rejected file and the Visitor subsequently selects a valid Pet_Photo, THE Frontend SHALL dismiss that Spooky_Message.
13. WHEN a generation finishes, THE Frontend SHALL keep the Pet_Photo selected so that the Visitor can try another costume without uploading the Pet_Photo again.

### Requirement 2: Costume Selection

**User Story:** As a Visitor, I want to choose a costume by uploading a photo or typing a description, so that I can dress my pet however I imagine.

#### Acceptance Criteria

1. THE Frontend SHALL provide a Costume_Photo upload control and a Costume_Description text input.
2. THE Frontend SHALL display a placeholder in the empty Costume_Description input that gives an example costume description, and SHALL remove the placeholder while the input contains at least 1 character.
3. THE Frontend SHALL display the hint "Using a costume photo? Add details here ✨" under the Costume_Description input.
4. THE Frontend SHALL display at least three Example_Chips, including "Wizard with purple hat", "Vampire cape", and "Pumpkin costume".
5. WHEN the Visitor clicks an Example_Chip, THE Frontend SHALL replace any existing content of the Costume_Description input with the chip text.
6. THE Frontend SHALL display a live character counter next to the Costume_Description input in the form "<current length> / 200", updated within 1 second of every change to the input.
7. THE Frontend SHALL limit the Costume_Description to a maximum of 200 characters.
8. IF the Visitor pastes text that would make the Costume_Description longer than 200 characters, THEN THE Frontend SHALL keep the first 200 characters and display a Spooky_Message stating that the text was trimmed to 200 characters.
9. WHEN the Visitor selects a valid Costume_Photo, THE Frontend SHALL apply the same acceptance, EXIF orientation correction, and automatic downscaling and compression rules as Requirement 1 criteria 1, 4, and 5, and SHALL display a preview of the Prepared_Image within 3 seconds on a typical phone.
10. IF the Visitor selects a Costume_Photo that is not a JPEG, PNG, or WebP image, is zero bytes, cannot be decoded as an image, or cannot be reduced to below 10 MB, THEN THE Frontend SHALL reject the file, display a Spooky_Message that states the accepted formats (JPG, PNG, WebP), display no preview for the rejected file, and retain any previously selected valid Costume_Photo.
11. WHEN the Visitor selects the remove action for the selected Costume_Photo, THE Frontend SHALL clear the Costume_Photo and its preview.
12. WHILE the Costume_Description is empty or contains only whitespace and no valid Costume_Photo is selected, THE Frontend SHALL disable the "Summon Costume" button.
13. WHILE no valid Pet_Photo is selected, THE Frontend SHALL disable the "Summon Costume" button.
14. WHILE a valid Pet_Photo is selected and either a valid Costume_Photo is selected or the Costume_Description contains at least 1 non-whitespace character, THE Frontend SHALL enable the "Summon Costume" button.

### Requirement 3: Costume Summoning Submission

**User Story:** As a Visitor, I want to click "Summon Costume", so that the pipeline starts creating my pet's costumed portrait.

#### Acceptance Criteria

1. WHEN the Visitor clicks the enabled "Summon Costume" button, THE Frontend SHALL submit the Costume_Request to the Backend within 500 milliseconds and show the Progress_Screen.
2. WHEN the Backend receives a Costume_Request, THE Backend SHALL validate that the Pet_Photo is present, has a JPEG, PNG, or WebP file type, and has a size greater than 0 bytes and no larger than 10 MB (10,485,760 bytes), where the 10 MB limit serves only as a safety net behind the Frontend downscaling.
3. IF the Backend receives a Costume_Request whose Pet_Photo is missing, has an unsupported file type, is empty, or is larger than 10 MB, THEN THE Backend SHALL reject the request within 2 seconds with an error response and a Spooky_Message that identifies the failed validation, SHALL NOT start the pipeline, and THE Frontend SHALL return the Visitor to the input screen with the Visitor's selected Pet_Photo, Costume_Photo, and Costume_Description retained.
4. WHEN both a Costume_Photo and a Costume_Description are provided, THE Backend SHALL use both as costume guidance for the same Costumed_Image.
5. IF a Costume_Photo is provided and its file type is not JPEG, PNG, or WebP, or its size is zero or greater than 10 MB, THEN THE Backend SHALL reject the request with an error response and a Spooky_Message, and SHALL NOT start the pipeline.
6. WHILE a Costume_Request is being processed, THE Frontend SHALL disable the "Summon Costume" button, so that no more than one Costume_Request per browser session is in progress at a time.
7. THE Backend SHALL process each Costume_Request without writing the Pet_Photo, Costume_Photo, or Costumed_Image to persistent server storage.
8. IF the Agent_Pipeline reaches the Pipeline_Timeout and no Costumed_Image exists, THEN THE Backend SHALL stop the pipeline, SHALL NOT count the request against any limit, and THE Frontend SHALL display the Spooky_Message "🧙 The cauldron went cold before the spell finished. Don't worry, it's on the house. Try again!"
9. IF the Agent_Pipeline reaches the Pipeline_Timeout while a Costumed_Image already exists, THEN THE Backend SHALL return that Costumed_Image to the Visitor with the not-verified message defined in Requirement 6, and SHALL count the request as 1 generation.

### Requirement 4: Gatekeeper Agent

**User Story:** As the operator of Pawleen, I want inputs checked before any expensive image call, so that the application avoids wasted cost and inappropriate content while still accepting every usable pet photo.

#### Acceptance Criteria

1. WHEN a Costume_Request passes limit and file validation, THE Gatekeeper_Agent SHALL return an accept or reject decision for the Costume_Request before the Costume_Maker_Agent is invoked, using a timeout of 30 seconds per attempt.
2. THE Gatekeeper_Agent SHALL use the vision-capable model named in the Environment_Config.
3. WHEN a Pet_Photo shows an animal of any species, including dogs, cats, birds, and rabbits, THE Gatekeeper_Agent SHALL accept the Pet_Photo, including a Pet_Photo with more than one animal.
4. WHEN a Pet_Photo shows a human together with at least one animal, THE Gatekeeper_Agent SHALL accept the Pet_Photo, and THE Costume_Maker_Agent SHALL dress only the animal or animals.
5. IF no animal can be identified in the Pet_Photo, THEN THE Gatekeeper_Agent SHALL reject the Costume_Request.
6. IF the Costume_Description is unintelligible, or contains sexual content, graphic violence, hate speech, or content that promotes illegal activity, THEN THE Gatekeeper_Agent SHALL reject the Costume_Request.
7. WHEN a Costume_Photo is provided and it gives any costume idea (clothing, accessories, a person or character in costume, or a drawing), THE Gatekeeper_Agent SHALL accept the Costume_Photo.
8. IF a Costume_Photo is provided and it contains sexual content, graphic violence, or hate symbols, or is completely unrelated to any costume idea, THEN THE Gatekeeper_Agent SHALL reject the Costume_Request.
9. IF the Gatekeeper_Agent rejects a Costume_Request, THEN THE Backend SHALL skip the Costume_Maker_Agent and Quality_Checker_Agent.
10. IF the Gatekeeper_Agent rejects a Costume_Request because no animal is present, THEN THE Frontend SHALL display the Spooky_Message "The spirits say that's not a pet! 👻" together with guidance to upload a photo that shows a pet.
11. IF the Gatekeeper_Agent rejects a Costume_Request because of the Costume_Description or Costume_Photo, THEN THE Frontend SHALL display the Spooky_Message "The spirits couldn't brew that one 👻 Try something like 'pirate hat with eye patch' or 'superhero cape'." together with at least three Example_Chips.
12. IF the Gatekeeper_Agent rejects a Costume_Request, THEN THE Backend SHALL NOT count the request against the Visitor_Daily_Limit, the Judge_Daily_Limit, or the Global_Daily_Cap.
13. IF a Gatekeeper_Agent attempt returns an error or does not return a decision within 30 seconds, THEN THE Backend SHALL perform one Silent_Retry.
14. IF the Silent_Retry of the Gatekeeper_Agent also returns an error or does not return a decision within 30 seconds, THEN THE Backend SHALL skip the Costume_Maker_Agent and Quality_Checker_Agent, SHALL NOT count the request against any limit, and THE Frontend SHALL display the Spooky_Message "👻 The Gatekeeper dozed off and couldn't check your pet. Your try wasn't used, so please try again!"

### Requirement 5: Costume Maker Agent

**User Story:** As a Visitor, I want my pet shown wearing the costume in a matching spooky setting while still looking like my pet, so that the result feels personal and fun.

#### Acceptance Criteria

1. WHEN the Gatekeeper_Agent accepts a Costume_Request, THE Costume_Maker_Agent SHALL generate one Costumed_Image using the image editing model named in the Environment_Config, with the Visitor's Prepared_Image of the pet and the requested costume as inputs.
2. THE Costume_Maker_Agent SHALL include in every image editing prompt an instruction to preserve the pet's species, fur or feather colors, markings, and facial features.
3. THE Costume_Maker_Agent SHALL include in every image editing prompt an instruction to produce a portrait-orientation image, with height greater than width.
4. THE Costume_Maker_Agent SHALL include in every image editing prompt an instruction to show the full pet and the full costume, centered, with a margin of at least 5% of the image width and height on each side, so that hats, ears, and paws are not cropped.
5. THE Costume_Maker_Agent SHALL include in every image editing prompt an instruction to place the pet in a Spooky_Scene.
6. WHEN the requested costume is a wizard, vampire, pumpkin, pirate, or ghost, THE Costume_Maker_Agent SHALL select the matching Spooky_Scene: a magical library with floating candles for a wizard, a dark castle under a red moon for a vampire, a foggy pumpkin patch at night for a pumpkin, a ghost ship on a stormy sea for a pirate, and a misty graveyard with fireflies for a ghost.
7. WHEN the requested costume is not one of the five costumes in criterion 6, THE Costume_Maker_Agent SHALL select a Spooky_Scene from a predefined list of spooky scenes that differs from the Spooky_Scene used for the previous Costume_Request from the same Browser_ID.
8. WHEN the Costume_Maker_Agent performs a Regeneration, THE Costume_Maker_Agent SHALL use the same Spooky_Scene as the first attempt.
9. THE Costume_Maker_Agent SHALL use a timeout of about 90 seconds for each image editing call.
10. IF the image editing call times out, THEN THE Backend SHALL NOT retry the call automatically, SHALL NOT count the request against any limit, and THE Frontend SHALL display a Spooky_Message stating that the costume could not be made and inviting the Visitor to try again.
11. IF the image editing call fails or returns no image, THEN THE Backend SHALL return a Spooky_Message that states the costume could not be made and invites the Visitor to try again, and SHALL retain nothing on the Backend, so that the Frontend retains the Visitor's Pet_Photo and costume selection for a retry without re-entering them.

### Requirement 6: Quality Checker Agent and Regeneration

**User Story:** As a Visitor, I want the result verified, so that I receive an image where my pet is recognizable, costumed, and fully visible.

#### Acceptance Criteria

1. WHEN the Costume_Maker_Agent produces a Costumed_Image, THE Quality_Checker_Agent SHALL evaluate the Costumed_Image using the vision-capable model named in the Environment_Config, using a timeout of 30 seconds per attempt.
2. WHEN the Quality_Checker_Agent evaluates a Costumed_Image, THE Quality_Checker_Agent SHALL report a pass or fail result for each of three checks (same pet, costume applied, no cropping) and SHALL report a failure reason for each failed check.
3. WHEN the Quality_Checker_Agent evaluates a Costumed_Image, THE Quality_Checker_Agent SHALL pass the same-pet check only if the pet in the Costumed_Image has the same species and the same primary fur or coat colors as the pet in the Pet_Photo.
4. WHEN the Quality_Checker_Agent evaluates a Costumed_Image, THE Quality_Checker_Agent SHALL pass the costume check only if the requested costume is visible on the pet in the Costumed_Image.
5. WHEN the Quality_Checker_Agent evaluates a Costumed_Image, THE Quality_Checker_Agent SHALL fail the cropping check only if the head, ears, hat, paws, or main costume is cut off by an image edge, and SHALL pass the cropping check when only a small part, such as a tail tip or a cape edge, touches the image border.
6. IF a Quality_Checker_Agent attempt returns an error or does not return a result within 30 seconds, THEN THE Agent_Pipeline SHALL perform one Silent_Retry of the Quality_Checker_Agent.
7. IF the Silent_Retry of the Quality_Checker_Agent also returns an error or does not return a result within 30 seconds, THEN THE Agent_Pipeline SHALL return the Costumed_Image under evaluation to the Visitor without a Regeneration, together with the Spooky_Message "🦉 Our owl inspector fell asleep, so this one wasn't double-checked. Hope you love it!"
8. IF the Quality_Checker_Agent reports a failed check on the first Costumed_Image, THEN THE Agent_Pipeline SHALL perform one Regeneration with a prompt that includes the failure reasons reported by the Quality_Checker_Agent.
9. WHEN the Regeneration completes, THE Quality_Checker_Agent SHALL evaluate the retry Costumed_Image using the same three checks, with the same timeout and Silent_Retry rule as criteria 1 and 6.
10. IF the retry Costumed_Image fails any check, THEN THE Agent_Pipeline SHALL return the Costumed_Image that passed more of the three checks, SHALL return the retry Costumed_Image when both images pass the same number of checks, and SHALL display the Spooky_Message "🔮 The spell came out a little wonky this time... Want to summon again?"
11. IF the Quality_Checker_Agent cannot evaluate the retry Costumed_Image after its Silent_Retry, THEN THE Agent_Pipeline SHALL return the retry Costumed_Image together with the not-verified Spooky_Message from criterion 7.
12. THE Agent_Pipeline SHALL perform no more than 1 Regeneration per Costume_Request.
13. THE Backend SHALL count exactly 1 generation against the applicable limit for each Costume_Request for which a Costumed_Image is returned to the Visitor, regardless of whether a Regeneration or a Silent_Retry occurred, and SHALL count no generation for any other outcome.

### Requirement 7: Live Progress Display

**User Story:** As a Visitor, I want to see each agent step as it happens, so that the wait feels engaging and transparent.

#### Acceptance Criteria

1. WHEN the Backend begins a Pipeline_Step, THE Backend SHALL send a progress event identifying that Pipeline_Step to the Frontend within 500 milliseconds of the step beginning.
2. WHILE the Agent_Pipeline is running, THE Backend SHALL send a Heartbeat_Event to the Frontend at least once every 10 seconds.
3. WHEN the Frontend receives a progress event, THE Progress_Screen SHALL display the message for that Pipeline_Step within 1 second of receipt.
4. WHEN the gatekeeping step is active, THE Progress_Screen SHALL display the message "The Gatekeeper is inspecting your pet..."
5. WHEN the costume generation step is active, THE Progress_Screen SHALL display the message "Brewing the costume spell..."
6. WHEN the quality checking step is active, THE Progress_Screen SHALL display the message "Checking the transformation..."
7. WHILE the costume generation step is active, THE Progress_Screen SHALL rotate through the lines "Stirring the cauldron...", "Adding a pinch of moonlight...", and "Almost there, the spell is thickening..." and SHALL change the displayed line every 4 seconds.
8. WHEN the Agent_Pipeline begins a Regeneration, THE Progress_Screen SHALL display a Spooky_Message stating that the spell is being recast, and SHALL display the current attempt number out of the maximum number of attempts.
9. THE Progress_Screen SHALL display each Pipeline_Step in exactly one of three states: complete (finished, marked with ✅), active (in progress, at most one step at a time, with a glow or animation), or pending (not yet started, dimmed).
10. THE Progress_Screen SHALL display a glowing progress bar that advances as Pipeline_Steps complete.
11. WHEN the Agent_Pipeline completes successfully, THE Progress_Screen SHALL display the final step message "🎃 Your spooky pet is ready!" and THE Frontend SHALL replace the Progress_Screen with the Result_View within 1 second of receiving the completion event.
12. IF the Agent_Pipeline ends in an error or rejection, THEN THE Frontend SHALL, within 1 second of receiving the failure event, replace the Progress_Screen with a Spooky_Message indicating the failure and a back button that returns the Visitor to the input form.
13. IF the Frontend receives no progress event, Heartbeat_Event, or completion event for 30 seconds while the Agent_Pipeline is running, THEN THE Frontend SHALL replace the Progress_Screen with a Spooky_Message indicating the connection was lost and a back button that returns the Visitor to the input form.
14. WHEN the Visitor activates the back button after a failure, a rejection, or a lost connection, THE Frontend SHALL return to the input form with the Pet_Photo, Costume_Photo, and Costume_Description still selected.

### Requirement 8: Result Display, Download, and Sharing

**User Story:** As a Visitor, I want to see, download, and share my pet's costumed portrait and quickly try another costume, so that I can keep and enjoy it.

#### Acceptance Criteria

1. WHEN the Agent_Pipeline returns a Costumed_Image, THE Result_View SHALL display the entire Costumed_Image in portrait orientation, with every pixel of the image visible and its original aspect ratio preserved, within 2 seconds of receiving the image.
2. WHEN the Result_View displays a Costumed_Image, THE Result_View SHALL display the Before_After_View with the original Pet_Photo next to the Costumed_Image.
3. WHEN the Result_View displays a Costumed_Image, THE Result_View SHALL display an enabled download button.
4. WHEN the Visitor clicks the download button, THE Frontend SHALL save the Costumed_Image to the Visitor's device as a PNG or JPEG image file at the full resolution returned by the Agent_Pipeline.
5. IF saving the Costumed_Image fails, THEN THE Frontend SHALL display an error message indicating the download failed and SHALL keep the Costumed_Image and the download button available for retry.
6. WHERE the Visitor's device is a mobile device that supports the device share menu, THE Result_View SHALL display a share button that opens the device share menu with the Costumed_Image.
7. IF the device share menu is unavailable or fails, THEN THE Frontend SHALL download the Costumed_Image instead.
8. WHEN the Result_View displays a Costumed_Image, THE Result_View SHALL display an enabled "Try another costume" button and an enabled "New pet" button.
9. WHEN the Visitor clicks "Try another costume", THE Frontend SHALL leave the Result_View and display the costume selection with the Pet_Photo still selected and the Costume_Photo and Costume_Description cleared.
10. WHEN the Visitor clicks "New pet", THE Frontend SHALL leave the Result_View and display the pet photo upload step with no previously selected photo or costume selection.
11. WHEN the Result_View displays a Costumed_Image, THE Result_View SHALL display the number of generations remaining for the Visitor on the current Usage_Day, reflecting the count after the just-completed generation, in the form "🕯️ 2 spells left tonight" (using "1 spell left tonight" for 1 and "0 spells left tonight" for 0).

### Requirement 9: Haunted Gallery

**User Story:** As a Visitor, I want a private gallery of my creations stored in my own browser, so that I can revisit, share, and download them later without any account.

#### Acceptance Criteria

1. WHEN the Agent_Pipeline returns a Costumed_Image, THE Frontend SHALL save the Costumed_Image to Browser_Storage (IndexedDB) within 2 seconds of receiving it, together with the costume name and the save date.
2. THE Haunted_Gallery SHALL display all Costumed_Images saved in Browser_Storage as thumbnails, ordered from newest to oldest by save time, and SHALL label each item with its costume name and date.
3. THE Haunted_Gallery SHALL display the hint "🦇 Your gallery lives in this browser. Download your favourites to keep them forever!"
4. WHEN the Visitor selects an item in the Haunted_Gallery, THE Frontend SHALL display that Costumed_Image at its original pixel dimensions, scaled down only if needed to fit the viewport, with a download button, a share button, and a delete button, within 1 second of the selection.
5. WHEN the Visitor activates the download button, THE Frontend SHALL download the selected Costumed_Image as an image file at its original resolution.
6. WHEN the Visitor activates the share button in the Haunted_Gallery, THE Frontend SHALL behave as defined in Requirement 8 criteria 6 and 7.
7. WHEN the Visitor reloads the page, THE Haunted_Gallery SHALL display the same Costumed_Images, in the same order, that were saved before the reload.
8. WHEN the Visitor activates the delete button for an item, THE Frontend SHALL display the confirmation "🪦 Banish this spell forever? This can't be undone." with the buttons "Banish" and "Keep it".
9. WHEN the Visitor selects "Banish", THE Frontend SHALL remove that Costumed_Image from Browser_Storage and from the Haunted_Gallery display within 1 second, and SHALL leave all other saved Costumed_Images unchanged.
10. WHEN the Visitor selects "Keep it", THE Frontend SHALL close the confirmation and leave all saved Costumed_Images unchanged.
11. THE Haunted_Gallery SHALL provide a "Clear my whole gallery" button that displays the same spooky confirmation with the buttons "Banish" and "Keep it".
12. WHEN the Visitor selects "Banish" in the confirmation for "Clear my whole gallery", THE Frontend SHALL remove all Costumed_Images from Browser_Storage and from the Haunted_Gallery display within 2 seconds.
13. WHILE Browser_Storage contains zero Costumed_Images, THE Haunted_Gallery SHALL display a Spooky_Message that invites the Visitor to summon a first costume.
14. THE Pawleen_App SHALL keep Haunted_Gallery contents only in the Visitor's own Browser_Storage and send zero gallery contents to the Backend.
15. IF Browser_Storage rejects a save because storage is full or unavailable, THEN THE Frontend SHALL display a Spooky_Message that states the image was not saved, keep the Costumed_Image available for download in the current session, and leave previously saved Costumed_Images unchanged.
16. IF Browser_Storage cannot be read when the page loads, THEN THE Frontend SHALL display a Spooky_Message that states the gallery could not be loaded and SHALL NOT delete any stored Costumed_Images.

### Requirement 10: Visitor Usage Limits

**User Story:** As the operator of Pawleen, I want per-visitor and global daily limits that treat each browser fairly, so that API costs stay controlled without blocking people who share a network.

#### Acceptance Criteria

1. THE Backend SHALL allow each non-Judge Visitor a maximum of Visitor_Daily_Limit successful generations per Usage_Day, where the Visitor_Daily_Limit defaults to 3 and is read from the Environment_Config.
2. THE Backend SHALL allow a maximum of Global_Daily_Cap successful generations per Usage_Day across all non-Judge Visitors, where the Global_Daily_Cap is a positive integer from 1 to 100,000 read from the Environment_Config at startup.
3. THE Backend SHALL identify a Visitor for limit purposes without requiring an account, primarily by the Browser_ID cookie and not by IP address alone.
4. WHEN a request arrives without a Browser_ID cookie, THE Backend SHALL issue a new random Browser_ID in a cookie.
5. IF the Visitor's browser does not return the Browser_ID cookie, THEN THE Backend SHALL fall back to a request-derived attribute for limit counting, so that the Global_Daily_Cap still bounds total generations.
6. WHEN a non-Judge Visitor has used the Visitor_Daily_Limit in the current Usage_Day and submits a Costume_Request, THE Backend SHALL reject the request without invoking the Gatekeeper_Agent, SHALL leave the generation counts unchanged, and SHALL return an error indicating the Visitor_Daily_Limit was reached, together with the number of seconds until the next reset.
7. WHEN the global generation count for the current Usage_Day equals the Global_Daily_Cap and a non-Judge Visitor submits a Costume_Request, THE Backend SHALL reject the request without invoking the Gatekeeper_Agent, SHALL leave the generation counts unchanged, and SHALL return an error indicating the Global_Daily_Cap was reached, together with the number of seconds until the next reset.
8. IF a Costume_Request is rejected because of the Visitor_Daily_Limit, THEN THE Frontend SHALL display a Spooky_Message within 1 second of receiving the rejection, in the form "🌙 The spirits need rest! Your spells return in 3 hours.", with the relative duration computed from the time until reset.
9. IF a Costume_Request is rejected because of the Global_Daily_Cap, THEN THE Frontend SHALL display a Spooky_Message within 1 second of receiving the rejection, in the form "🦇 The photo booth is closed for the night. It reopens in 3 hours!", with the relative duration computed from the time until reset.
10. THE Frontend SHALL express every reset time as a relative duration, rounded up to whole hours when at least 1 hour remains and to whole minutes otherwise, and SHALL NOT display reset times in UTC.
11. WHEN the Backend receives a Costume_Request from a non-Judge Visitor, THE Backend SHALL check the Visitor_Daily_Limit and the Global_Daily_Cap before invoking the Gatekeeper_Agent.
12. WHEN a new Usage_Day begins, THE Backend SHALL reset the per-Browser_ID and global generation counts to 0.
13. WHEN the Frontend requests usage status, THE Backend SHALL return the number of generations remaining for the requesting Browser_ID, as an integer from 0 to the applicable daily limit.
14. THE Backend SHALL keep generation counts in memory or other non-database storage.
15. IF the Backend restarts, THEN THE Backend SHALL treat all generation counts as 0 for the current Usage_Day.
16. WHEN two or more Costume_Requests from the same Browser_ID arrive concurrently, THE Backend SHALL ensure the number of accepted requests does not exceed the remaining allowance.
17. IF a Costume_Request is rejected, refused, fails, or times out at any step, THEN THE Backend SHALL leave the Visitor_Daily_Limit, Judge_Daily_Limit, and Global_Daily_Cap counts unchanged.

### Requirement 11: Judge Pass

**User Story:** As a Judge, I want to unlock a larger allowance with a secret code, so that I can evaluate Pawleen thoroughly.

#### Acceptance Criteria

1. WHEN the Backend starts, THE Backend SHALL read the Judge_Pass value from the Environment_Config.
2. IF the Judge_Pass value is absent or an empty string in the Environment_Config, THEN THE Backend SHALL treat every presented Judge_Pass as invalid and keep the Visitor_Daily_Limit in effect for all Visitors.
3. WHEN the Visitor opens the Pawleen_App with a non-empty `pass` URL query parameter, THE Frontend SHALL submit that value to the Backend for validation within 1 second of page load.
4. WHEN the Backend accepts a Judge_Pass presented through the `pass` URL query parameter, THE Frontend SHALL remove the `pass` parameter from the address bar without reloading the page.
5. THE Frontend SHALL display the Judge_Pass_Box labeled "Have a judge pass?" for entering a Judge_Pass, accepting input of 1 to 128 characters.
6. WHEN the Visitor submits a value in the Judge_Pass_Box, THE Backend SHALL validate the value against the Judge_Pass and return the validation result within 2 seconds.
7. WHEN a valid Judge_Pass is presented, THE Backend SHALL apply the Judge_Daily_Limit to the Browser_ID that presented it instead of the Visitor_Daily_Limit for the remainder of the current Usage_Day, where the Judge_Daily_Limit defaults to 20 and is read from the Environment_Config.
8. THE Backend SHALL count Judge generations separately for each Browser_ID, and separately from the Global_Daily_Cap and from non-Judge Visitor counts, so that a Judge generation does not increase either of those counts and one Judge's usage does not reduce another Judge's allowance.
9. IF an invalid Judge_Pass is presented, THEN THE Frontend SHALL display the Spooky_Message "🗝️ That key doesn't fit this crypt... Please check your judge pass.", keep the Visitor_Daily_Limit in effect, and leave any previously stored Judge_Pass in Session_Storage unchanged.
10. WHEN 5 invalid Judge_Pass attempts have been presented from the same Browser_ID, THE Backend SHALL reject all further Judge_Pass validation requests from that Browser_ID for 1 hour, and THE Frontend SHALL display a Spooky_Message stating that the crypt is sealed and the relative time after which the Visitor can try again.
11. IF the Backend does not respond to a Judge_Pass validation request within 10 seconds or returns an error, THEN THE Frontend SHALL display a Spooky_Message stating that the pass could not be checked, keep the Visitor_Daily_Limit in effect, and allow the Visitor to resubmit.
12. WHEN a valid Judge_Pass is accepted, THE Frontend SHALL display the Spooky_Message "🔑 Welcome, honoured judge! The crypt is open, with 20 spells for tonight.", in which the number equals the Judge's remaining generations as a whole number from 0 to the Judge_Daily_Limit.
13. THE Backend SHALL compare the presented value to the Judge_Pass using a constant-time comparison.
14. WHEN a valid Judge_Pass is accepted, THE Frontend SHALL store the Judge_Pass in Session_Storage so that it persists until the browser session ends and is removed afterward.
15. THE Backend SHALL omit the Judge_Pass value from all responses and logs.

### Requirement 12: OpenAI Credit and Service Failure Handling

**User Story:** As a Visitor, I want friendly messages when the service cannot continue, so that I understand what happened and what to do next.

#### Acceptance Criteria

1. IF the OpenAI API reports insufficient quota or an exhausted balance, THEN THE Backend SHALL return a failure response that identifies the failure category as "credits depleted", AND THE Frontend SHALL display the Spooky_Message "🧪 Our cauldron is out of magic. Please come back later!" within 1 second of receiving that response.
2. IF the OpenAI API returns a server error (5xx) or a network error, THEN THE Backend SHALL return a failure response that identifies the failure category as "temporary failure", AND THE Frontend SHALL display the Spooky_Message "🌩️ A storm is disturbing the spirits. Try again in a moment!" within 1 second of receiving that response.
3. IF an OpenAI API call exceeds the timeout defined for its step in Requirements 4, 5, and 6 and is not covered by a Silent_Retry, THEN THE Backend SHALL return a failure response that identifies the failure category as "temporary failure" and THE Frontend SHALL display the message defined for that step.
4. IF the OpenAI API refuses a request for safety reasons, THEN THE Backend SHALL return a failure response that identifies the failure category as "refused by AI safety", AND THE Frontend SHALL display the Spooky_Message "🔮 The spirits refused this spell. Try a different costume idea!" together with at least three Example_Chips.
5. IF the OpenAI API call fails for any reason, THEN THE Backend SHALL NOT count the failed Costume_Request against the Visitor_Daily_Limit, the Judge_Daily_Limit, or the Global_Daily_Cap, so that each counter has the same value after the failure as before the request.
6. IF the OpenAI API call fails, THEN THE Frontend SHALL keep the Visitor's uploaded photo and selected options in place, and SHALL re-enable the submit control so the Visitor can submit again without re-uploading.
7. THE Backend SHALL omit the OpenAI API key, stack traces, and raw OpenAI error text from every response sent to the Frontend.
8. WHEN the OpenAI API reports an exhausted balance, THE Backend SHALL write one log entry that records the event time and failure category, AND the log entry SHALL NOT contain the OpenAI API key or any other secret value.

### Requirement 13: Configuration and Secrets

**User Story:** As the operator of Pawleen, I want secrets and model names configured through the environment, so that no secret or model choice is hardcoded.

#### Acceptance Criteria

1. WHEN the Backend starts, THE Backend SHALL read the OpenAI API key from the Environment_Config.
2. WHEN the Backend starts, THE Backend SHALL read the image editing model name from the Environment_Config.
3. WHEN the Backend starts, THE Backend SHALL read the vision-capable model name from the Environment_Config.
4. WHEN the Backend starts, THE Backend SHALL read the Judge_Pass, Visitor_Daily_Limit, Judge_Daily_Limit, and Global_Daily_Cap from the Environment_Config.
5. WHERE the Visitor_Daily_Limit or Judge_Daily_Limit is not set in the Environment_Config, THE Backend SHALL use the default value of 3 for the Visitor_Daily_Limit and 20 for the Judge_Daily_Limit.
6. IF Visitor_Daily_Limit, Judge_Daily_Limit, or Global_Daily_Cap is set but is not a whole number between 1 and 1,000,000, THEN THE Backend SHALL log the names of the invalid variables, refuse to run the Agent_Pipeline, and keep running other Backend functions.
7. THE Pawleen_App SHALL keep the OpenAI API key and Judge_Pass out of source code, Frontend assets, and version control.
8. THE Pawleen_App repository SHALL list the `.env` file in `.gitignore`.
9. THE Pawleen_App repository SHALL include a `.env.example` file that lists every variable name with a placeholder value and contains no real secret value.
10. IF the OpenAI API key, the image editing model name, the vision-capable model name, or the Global_Daily_Cap is missing or is an empty string at startup, THEN THE Backend SHALL log the names of the missing variables, refuse to run the Agent_Pipeline, and keep running other Backend functions.
11. IF the Backend refuses to run the Agent_Pipeline because of an Environment_Config error, THEN THE Backend SHALL omit the values of all Environment_Config variables from its log output and return an error response to any request that would start the Agent_Pipeline, AND THE Frontend SHALL display the Spooky_Message "🕸️ The photo booth isn't open yet. The spirits are still setting up!"

### Requirement 14: Hosting and Delivery

**User Story:** As the operator of Pawleen, I want a single deployable web service with reproducible dependencies, so that hosting on Render stays simple.

#### Acceptance Criteria

1. WHEN a client sends a request for the Frontend entry page or a Frontend static asset, THE Backend SHALL return that file from the same FastAPI web service process that serves the API, and THE Backend SHALL NOT require a separate web server process.
2. WHEN a client sends a request for a Frontend page or static asset path that does not exist, THE Backend SHALL return a 404 not-found response and SHALL NOT return the entry page content.
3. THE 404 response for a missing Frontend page or static asset SHALL display the Spooky_Message "🪦 This page has been buried..." together with a button that returns the Visitor to the booth.
4. WHEN the Backend starts, THE Backend SHALL listen on the TCP port given by the PORT environment variable on host 0.0.0.0.
5. IF the PORT environment variable is not set, THEN THE Backend SHALL listen on port 8000.
6. IF the PORT environment variable is set to a value that is not an integer from 1 to 65535, THEN THE Backend SHALL exit with a non-zero exit code and write an error message to standard error that names the invalid PORT value.
7. THE Pawleen_App repository SHALL include a Python dependency manifest (`requirements.txt`) that lists every third-party package the Backend imports with an exact pinned version, and a single-line start command that launches the Backend with no manual steps after the dependencies are installed.
8. WHEN a client sends a GET request to the health check endpoint, THE Backend SHALL respond within 500 milliseconds with a success response that indicates the service is running.

### Requirement 15: Haunting, Responsive User Interface

**User Story:** As a Visitor, I want a polished haunted Halloween experience on any device, so that using Pawleen is delightful.

#### Acceptance Criteria

1. THE Frontend SHALL be designed mobile-first and remain fully usable at viewport widths from 320 px to 1920 px, with the document width equal to the viewport width (no horizontal scrollbar) at every width in that range.
2. THE Frontend SHALL render a dark theme in which the page background has a relative luminance of at most 0.05 and purple and orange are the two accent colors used for primary buttons, headings, and links.
3. THE Frontend SHALL display an animated fog effect in the page background that loops continuously and does not intercept pointer or keyboard input to the content above it.
4. THE Frontend SHALL display every primary button with a visible glow effect (a colored shadow around the button) in its default, hover, and keyboard-focus states.
5. THE Frontend SHALL render headings in a spooky display font and body text in a legible font, and SHALL fall back to a generic serif or sans-serif font if either font fails to load within 3 seconds.
6. THE Frontend SHALL maintain a contrast ratio of at least 4.5:1 for body text, and at least 3:1 for large text (18 pt or larger, or 14 pt bold or larger) and for button borders and focus indicators, against their backgrounds.
7. WHILE the viewport width is below 768 px, THE Frontend SHALL size every interactive control to at least 44 px by 44 px.
8. WHERE the Visitor's system setting requests reduced motion, THE Frontend SHALL disable the fog animation, the floating bats and ghosts, the candle flicker, the fog-clearing reveal, and all other non-essential animations (any animation not required to convey state or progress), and SHALL render the fog as a static background and show the Costumed_Image immediately.
9. THE Frontend SHALL write every label, button, and message in a spooky tone and SHALL include in each button label and message the plain action or next step available to the Visitor, in at most 160 characters per message.
10. THE Frontend SHALL provide a navigation control to switch between the booth view and the Haunted_Gallery, reachable in at most 1 interaction from every screen and visible at every viewport width from 320 px to 1920 px.
11. THE Frontend SHALL provide a non-empty text alternative for every non-decorative image and SHALL mark decorative images as hidden from assistive technology.
12. THE Frontend SHALL make every interactive control reachable and operable using the keyboard alone, in a logical tab order, with a visible focus indicator.
13. WHEN the Result_View displays a new Costumed_Image, THE Frontend SHALL play a fog-clearing reveal animation that uncovers the Costumed_Image.
14. THE Frontend SHALL style the Pet_Photo upload area as a glowing portal and the costume area as a bubbling cauldron.
15. THE Frontend SHALL display subtle floating bats or ghosts and a flickering candle glow in the page background, without intercepting pointer or keyboard input.
16. THE Frontend SHALL use a ghost with a paw print as the Pawleen logo and as the browser tab icon.
17. THE Frontend SHALL provide optional spooky sound effects that are off by default, and SHALL provide a Sound_Toggle, reachable from every screen, that turns the sound effects on or off.
18. THE Frontend SHALL create the application background fresh with CSS or code and SHALL NOT load any external image for the background.

### Requirement 16: Privacy and Data Handling

**User Story:** As a Visitor, I want my photos kept private and to understand how they are used, so that I can trust Pawleen with pictures of my pet.

#### Acceptance Criteria

1. WHEN a Costume_Request completes successfully, THE Backend SHALL discard the uploaded images and all generated images from memory within 5 seconds of sending the response to the Visitor.
2. IF a Costume_Request fails or is cancelled, THEN THE Backend SHALL discard the uploaded images and any generated images from memory within 5 seconds of the failure or cancellation.
3. THE Backend SHALL NOT write uploaded images or generated images to disk, a database, or any persistent storage.
4. THE Backend SHALL transmit uploaded images to no external service other than the OpenAI API.
5. WHEN the Visitor first loads the main page, THE Frontend SHALL display the Privacy_Banner stating that photos are processed by OpenAI, that photos are not stored on the servers, that the Haunted_Gallery is stored only in the Visitor's browser, and that an anonymous Browser_ID cookie is used to count daily spells.
6. WHEN the Visitor dismisses the Privacy_Banner, THE Frontend SHALL hide the Privacy_Banner and record the dismissal in Preference_Storage, so that the Privacy_Banner is not shown again on later visits from the same browser.
7. THE Frontend SHALL display on every screen a footer line with the text "🔒 Your photos are only used to create your costume (processed by OpenAI) and are never stored on our servers. Your gallery stays in your browser."
8. THE Backend SHALL NOT include image content, including raw bytes and base64-encoded data, in application log entries at any log level.
